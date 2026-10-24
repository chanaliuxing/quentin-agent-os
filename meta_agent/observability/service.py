# meta_agent/observability/service.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Optional, Any, Iterable
from pathlib import Path
import json
import time
import datetime as dt

from meta_agent.observability.snapshot import (
    SystemSnapshot, LoopStatus, PatchStats, SkillStats, GapStats, ResearchStats, BlueprintStats, BlueprintEffectStats
)
from meta_agent.evolution.schedule_config import SelfEvolutionScheduleConfig
from meta_agent.evolution.schedule_state import SelfEvolutionStateStore
from meta_agent.skills.registry import SkillRegistry
from meta_agent.blueprint.version_store import BlueprintVersionStore
from meta_agent.blueprint.impact_analyzer import BlueprintImpactAnalyzer
from quentin.traces.core import JsonlTraceRecorder

trace = JsonlTraceRecorder(repo_root=".")

@dataclass
class ObservabilityConfig:
    blueprint_versions_root: Path = Path("data/blueprint/versions")
    metrics_log_path: Path = Path("logs/runtime_metrics.jsonl")
    blueprint_impact_max_versions: int = 20
    blueprint_impact_window_hours: int = 24
    top_recent_skill_count: int = 10

class ObservabilityService:
    def __init__(self, obs_config: Optional[ObservabilityConfig] = None, sched_config: Optional[SelfEvolutionScheduleConfig] = None, state_store: Optional[SelfEvolutionStateStore] = None, skill_registry: Optional[SkillRegistry] = None):
        self.obs_config = obs_config or ObservabilityConfig()
        self.sched_config = sched_config or SelfEvolutionScheduleConfig()
        self.state_store = state_store or SelfEvolutionStateStore()
        self.skill_registry = skill_registry or SkillRegistry()
        self._blueprint_store = BlueprintVersionStore(self.obs_config.blueprint_versions_root)
        self._blueprint_impact_analyzer = BlueprintImpactAnalyzer(
            blueprint_versions_root=self.obs_config.blueprint_versions_root,
            metrics_log_path=self.obs_config.metrics_log_path,
            window_hours=self.obs_config.blueprint_impact_window_hours,
        )

    def build_snapshot(self) -> SystemSnapshot:
        now_ts = time.time()
        state = self.state_store.load()
        
        # New blueprint related maps for Analyzer
        blueprint_impl_status = self._collect_blueprint_impl_status()
        blueprint_gaps_map = self._collect_blueprint_gaps()
        blueprint_skills_map = self._collect_blueprint_skills()
        blueprint_tests_map = self._collect_blueprint_tests()
        blueprint_self_evo_map = self._collect_blueprint_self_evo()


        return SystemSnapshot(
            loops=self._build_loop_status(state, now_ts),
            patches=self._build_patch_stats(now_ts),
            skills=self._build_skill_stats(),
            gaps=self._build_gap_stats(),
            research=self._build_research_stats(now_ts),
            blueprint=self._build_blueprint_stats(now_ts),
            blueprint_effects=self._build_blueprint_effect_stats(),
            blueprint_impl_status=blueprint_impl_status,
            blueprint_gaps=blueprint_gaps_map,
            blueprint_skills=blueprint_skills_map,
            blueprint_tests=blueprint_tests_map,
            blueprint_self_evo=blueprint_self_evo_map,
        )

    def _build_blueprint_effect_stats(self) -> BlueprintEffectStats:
        try:
            report = self._blueprint_impact_analyzer.build_report(limit_versions=self.obs_config.blueprint_impact_max_versions)
        except Exception:
            return BlueprintEffectStats()

        stats = {"beneficial": 0, "neutral": 0, "harmful": 0, "unknown": 0}
        last_ben_id = last_ben_at = None
        last_harm_id = last_harm_at = None

        for item in report.items:
            stats[item.effect_label] = stats.get(item.effect_label, 0) + 1
            if item.effect_label == "beneficial" and last_ben_id is None:
                last_ben_id, last_ben_at = item.version_id, item.created_at
            elif item.effect_label == "harmful" and last_harm_id is None:
                last_harm_id, last_harm_at = item.version_id, item.created_at

        return BlueprintEffectStats(
            total_analyzed=len(report.items),
            beneficial=stats["beneficial"], neutral=stats["neutral"], harmful=stats["harmful"], unknown=stats["unknown"],
            last_beneficial_version_id=last_ben_id, last_beneficial_at=last_ben_at,
            last_harmful_version_id=last_harm_id, last_harmful_at=last_harm_at,
        )

    # --- Compatibility methods for Blueprint Coverage Analyzer ---
    def _collect_blueprint_impl_status(self) -> Dict[str, Any]:
        """
        Collect lightweight implementation status signals for known blueprint sections.

        This is intentionally heuristic-driven: the blueprint coverage report is meant
        to be runnable locally without requiring a full static analysis pipeline.
        """
        def count_comment_fixups(text: str) -> int:
            import re

            # NOTE: Avoid treating generic task markers as blueprint gaps; we only
            # count explicit fixup markers that are intended as actionable debt.
            return len(re.findall(r"(^|\\s)#\\s*FIXUP\\b", text, flags=re.MULTILINE))

        def module_file_from_dotted_path(dotted: str) -> tuple[Path, str]:
            parts = dotted.split(".")
            symbol = parts[-1]
            mod = ".".join(parts[:-1])
            file_path = Path(*mod.split(".")).with_suffix(".py")
            return file_path, symbol

        def symbol_present(file_path: Path, symbol: str) -> bool:
            import ast

            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return False

            try:
                tree = ast.parse(text)
            except SyntaxError:
                tree = None

            if tree is not None:
                for node in tree.body:
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
                        return True

            # Accept simple re-export wrappers.
            if f"import {symbol}" in text:
                return True
            if "__all__" in text and symbol in text:
                return True
            if "re-export" in text.lower() and symbol in text:
                return True
            return False

        section_checks: Dict[str, List[Path]] = {
            "memory.fabric": [
                Path("quentin/memory/fabric.py"),
                Path("quentin/memory/store_sqlite.py"),
            ],
            "skills.mining": [
                Path("quentin/skills/miner.py"),
                Path("quentin/skills/promotion.py"),
                Path("quentin/skills/library.py"),
            ],
            "patchflow.core": [
                Path("meta_agent/self_programming/engine_v2.py"),
                Path("meta_agent/self_programming/test_runner.py"),
                Path("meta_agent/self_programming/governance.py"),
            ],
        }
        section_symbols: Dict[str, str] = {}

        yaml_path = Path("blueprint/meta_agent_v3.yaml")
        if yaml_path.exists():
            try:
                import yaml  # type: ignore

                raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                for layer in raw.get("layers") or []:
                    lid = layer.get("id")
                    for m in (layer.get("modules") or []):
                        mid = m.get("id")
                        dotted = m.get("path")
                        if not (lid and mid and dotted):
                            continue
                        sec_id = f"{lid}.{mid}"
                        file_path, sym = module_file_from_dotted_path(str(dotted))
                        section_checks.setdefault(sec_id, []).append(file_path)
                        section_symbols[sec_id] = sym
            except Exception:
                pass

        out: Dict[str, Any] = {}
        for sec_id, paths in section_checks.items():
            present = any(p.exists() for p in paths)
            open_todos = 0
            last_changed_at = None
            for p in paths:
                if not p.exists():
                    continue
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    text = ""
                open_todos += count_comment_fixups(text)
                try:
                    mtime = dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat()
                    if last_changed_at is None or mtime > last_changed_at:
                        last_changed_at = mtime
                except Exception:
                    pass

            sym = section_symbols.get(sec_id)
            if sym:
                present = any(p.exists() and symbol_present(p, sym) for p in paths)

            out[sec_id] = {
                "present": bool(present),
                "open_todos": int(open_todos),
                "last_changed_at": last_changed_at,
                "signals": {
                    "files_checked": [str(p) for p in paths],
                    "expected_symbol": sym,
                },
            }
        return out

    def _collect_blueprint_gaps(self) -> Dict[str, Any]:
        # For now, treat "gaps" as explicit FIXUP markers in canonical files. A future
        # implementation can plug into a dedicated gap tracker.
        impl_map = self._collect_blueprint_impl_status()
        out: Dict[str, Any] = {}
        for sec_id, info in impl_map.items():
            open_todos = int(info.get("open_todos", 0))
            out[sec_id] = {"open_gaps": 0, "open_todos": open_todos}
        return out

    def _collect_blueprint_skills(self) -> Dict[str, Any]:
        # Map blueprint areas to whether there are active skills registered.
        # This is intentionally conservative: "has_active_skills" is true if
        # the registry has any enabled skills for the domain prefix.
        out: Dict[str, Any] = {}
        try:
            skills = list(self.skill_registry.list_skills())
        except Exception:
            skills = []

        def has_domain(prefix: str) -> bool:
            for s in skills:
                domain = getattr(s, "domain", None) or getattr(s, "category", None)
                if isinstance(domain, str) and domain.startswith(prefix):
                    return True
            return False

        out["memory.fabric"] = {"has_active_skills": has_domain("memory")}
        out["skills.mining"] = {"has_active_skills": has_domain("skills")}
        out["patchflow.core"] = {"has_active_skills": has_domain("self_programming") or has_domain("patch")}
        return out

    def _collect_blueprint_tests(self) -> Dict[str, Any]:
        # Lightweight test signals: check for relevant test files.
        # Avoid importing pytest or running tests here.
        out: Dict[str, Any] = {}
        test_paths = list(Path("tests").rglob("test_*.py")) if Path("tests").exists() else []
        test_text_cache: Dict[Path, str] = {}

        def count_mentions(needles: Iterable[str]) -> int:
            total = 0
            for p in test_paths:
                try:
                    text = test_text_cache.get(p)
                    if text is None:
                        text = p.read_text(encoding="utf-8", errors="ignore")
                        test_text_cache[p] = text
                except Exception:
                    continue
                if any(n in text for n in needles):
                    total += 1
            return total

        out["memory.fabric"] = {"has_tests": count_mentions(["MemoryFabric", "quentin.memory"]) > 0}
        out["skills.mining"] = {"has_tests": count_mentions(["skill", "Skill", "quentin.skills"]) > 0}
        out["patchflow.core"] = {"has_tests": count_mentions(["SelfProgramming", "engine_v2", "meta_agent.self_programming"]) > 0}

        yaml_path = Path("blueprint/meta_agent_v3.yaml")
        if yaml_path.exists():
            try:
                import yaml  # type: ignore

                raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                for layer in raw.get("layers") or []:
                    lid = layer.get("id")
                    for m in (layer.get("modules") or []):
                        mid = m.get("id")
                        dotted = m.get("path")
                        if not (lid and mid and dotted):
                            continue
                        sec_id = f"{lid}.{mid}"
                        symbol = str(dotted).split(".")[-1]
                        out[sec_id] = {"has_tests": count_mentions([symbol]) > 0}
            except Exception:
                pass
        return out

    def _collect_blueprint_self_evo(self) -> Dict[str, Any]:
        # Use persisted state store timestamps if available; otherwise fall back to file mtimes.
        state = self.state_store.load()
        loop_runs = state.get("loop_runs") if isinstance(state, dict) else {}
        if not isinstance(loop_runs, dict):
            loop_runs = {}

        def touched(loop_name: str) -> Dict[str, Any]:
            info = loop_runs.get(loop_name) if isinstance(loop_runs, dict) else None
            if isinstance(info, dict):
                last = info.get("last_run_at")
                if isinstance(last, str):
                    return {"touched_recently": True, "last_touched_at": last}
            return {"touched_recently": False, "last_touched_at": None}

        out = {
            "memory.fabric": touched("sleep"),
            "skills.mining": touched("skill_mining"),
            "patchflow.core": touched("self_programming"),
        }

        yaml_path = Path("blueprint/meta_agent_v3.yaml")
        if yaml_path.exists():
            try:
                import yaml  # type: ignore

                raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                for layer in raw.get("layers") or []:
                    lid = layer.get("id")
                    for m in (layer.get("modules") or []):
                        mid = m.get("id")
                        if not (lid and mid):
                            continue
                        sec_id = f"{lid}.{mid}"
                        loop_hint = "self_programming"
                        if lid == "L1":
                            loop_hint = "sleep"
                        elif lid == "L0":
                            loop_hint = "immune"
                        elif lid == "L2":
                            loop_hint = "blueprint_improvement"
                        out.setdefault(sec_id, touched(loop_hint))
            except Exception:
                pass

        return out


    # Other build methods...
    def _build_loop_status(self, state, now_ts) -> List[LoopStatus]:
        # Minimal loop stats: driven by schedule config and persisted state (if any).
        loop_names = [
            "blueprint_improvement",
            "sleep",
            "immune",
            "self_programming",
        ]
        loop_runs = state.get("loop_runs") if isinstance(state, dict) else {}
        out: List[LoopStatus] = []
        for name in loop_names:
            info = loop_runs.get(name) if isinstance(loop_runs, dict) else None
            runs_today = 0
            last_run_at = None
            if isinstance(info, dict):
                runs_today = int(info.get("runs_today", 0) or 0)
                last_run_at = info.get("last_run_at")
                if last_run_at is not None and not isinstance(last_run_at, str):
                    last_run_at = None
            out.append(
                LoopStatus(
                    name=name,
                    runs_today=runs_today,
                    last_run_at=last_run_at,
                    next_earliest_run_at=None,
                    max_runs_per_day=self.sched_config.max_runs_per_day(name),
                )
            )
        return out

    def _build_skill_stats(self) -> SkillStats:
        try:
            skills = list(self.skill_registry.list_skills())
        except Exception:
            skills = []
        return SkillStats(total_skills=len(skills))

    def _build_blueprint_stats(self, now_ts) -> BlueprintStats:
        # Minimal blueprint stats using version store.
        try:
            versions = list(self._blueprint_store.list_versions())
        except Exception:
            versions = []
        last = versions[0] if versions else None
        last_id = getattr(last, "version_id", None) or getattr(last, "id", None)
        last_at = getattr(last, "created_at", None)
        if last_at is not None and not isinstance(last_at, str):
            last_at = None
        return BlueprintStats(
            total_versions=len(versions),
            last_version_id=last_id,
            last_version_at=last_at,
        )

    def _build_patch_stats(self, now_ts: float) -> PatchStats:
        """
        Patch stats across:
        - `meta_agent.patches.store.PatchStore` (`data/patches.json`)
        - PatchFlow queue (`data/patches/patch_queue.jsonl`)
        """
        from datetime import datetime, timezone

        now = datetime.fromtimestamp(now_ts, tz=timezone.utc)
        last_24h = now.timestamp() - 24 * 3600

        def _parse_dt(v: Any) -> Optional[datetime]:
            if isinstance(v, datetime):
                return v.astimezone(timezone.utc)
            if isinstance(v, str) and v:
                try:
                    dtv = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
                    if dtv.tzinfo is None:
                        dtv = dtv.replace(tzinfo=timezone.utc)
                    return dtv.astimezone(timezone.utc)
                except Exception:
                    return None
            return None

        total = applied = rejected = pending = 0
        last_24h_new = last_24h_applied = last_24h_rejected = 0

        # PatchStore
        try:
            from meta_agent.patches.store import PatchStore

            store = PatchStore()
            patches = store.list_patches(limit=5000)
        except Exception:
            patches = []

        for p in patches:
            total += 1
            status = str(getattr(p, "status", "") or "").lower()
            created = _parse_dt(getattr(p, "created_at", None))
            if created and created.timestamp() >= last_24h:
                last_24h_new += 1

            if status == "applied":
                applied += 1
                if created and created.timestamp() >= last_24h:
                    last_24h_applied += 1
            elif status in ("rejected", "blocked", "failed"):
                rejected += 1
                if created and created.timestamp() >= last_24h:
                    last_24h_rejected += 1
            else:
                pending += 1

        # PatchFlow queue
        try:
            from meta_agent.patchflow.queue import PatchQueue

            q = PatchQueue()
            q_items = q.load_all()
        except Exception:
            q_items = []

        for p in q_items:
            total += 1
            status = str(getattr(p, "status", "") or "").lower()
            created = _parse_dt(getattr(p, "created_at", None))
            if created and created.timestamp() >= last_24h:
                last_24h_new += 1

            if status == "applied":
                applied += 1
                if created and created.timestamp() >= last_24h:
                    last_24h_applied += 1
            elif status in ("rejected", "blocked"):
                rejected += 1
                if created and created.timestamp() >= last_24h:
                    last_24h_rejected += 1
            else:
                pending += 1

        return PatchStats(
            total_patches=int(total),
            applied_patches=int(applied),
            rejected_patches=int(rejected),
            pending_patches=int(pending),
            last_24h_new=int(last_24h_new),
            last_24h_applied=int(last_24h_applied),
            last_24h_rejected=int(last_24h_rejected),
        )

    def _build_gap_stats(self) -> GapStats:
        """
        Aggregate gaps from the blueprint coverage maps.
        """
        gaps_map = self._collect_blueprint_gaps()
        open_todos = 0
        open_gaps = 0
        for _, v in (gaps_map or {}).items():
            if not isinstance(v, dict):
                continue
            open_todos += int(v.get("open_todos", 0) or 0)
            open_gaps += int(v.get("open_gaps", 0) or 0)

        total = open_todos + open_gaps
        return GapStats(
            total_gaps=int(total),
            open_gaps=int(total),
            closed_gaps=0,
            low_quality_count=0,
        )

    def _build_research_stats(self, now_ts: float) -> ResearchStats:
        """
        Minimal research stats from `data/research/eval_results.jsonl`.
        """
        from datetime import datetime, timezone

        now = datetime.fromtimestamp(now_ts, tz=timezone.utc)
        cutoff = now.timestamp() - 24 * 3600

        path = Path("data/research/eval_results.jsonl")
        if not path.exists():
            return ResearchStats()

        total = 0
        last_24h = 0
        by_source: Dict[str, int] = {}
        last_at: Optional[str] = None

        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue

                    total += 1
                    t = rec.get("finished_at") or rec.get("started_at")
                    t_dt = None
                    if isinstance(t, str):
                        try:
                            t_dt = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
                        except Exception:
                            t_dt = None
                    if t_dt and t_dt.timestamp() >= cutoff:
                        last_24h += 1
                    if isinstance(t, str) and (last_at is None or t > last_at):
                        last_at = t

                    src = rec.get("target_type") or rec.get("variant_id") or "unknown"
                    by_source[str(src)] = by_source.get(str(src), 0) + 1
        except Exception:
            return ResearchStats()

        return ResearchStats(
            total_research_calls=int(total),
            last_24h_research_calls=int(last_24h),
            by_source=by_source,
            last_research_at=last_at,
        )
