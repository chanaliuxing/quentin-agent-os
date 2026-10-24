# meta_agent/blueprint/gap_quality.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
import subprocess
import json
import logging

from meta_agent.monitoring.status_snapshot import StatusSnapshot
from quentin.traces.core import JsonlTraceRecorder

logger = logging.getLogger(__name__)
trace = JsonlTraceRecorder(repo_root=".")


@dataclass
class GapQualityScore:
    """对某个 Blueprint gap 当前实现质量的打分。"""

    overall_score: float             # 0-10，越高越好
    impl_maturity: str               # "none"|"draft"|"partial"|"stable"
    has_tests: bool
    risk_level: str                  # "low"|"medium"|"high"
    issues: List[str] = field(default_factory=list)
    suggested_actions: List[str] = field(default_factory=list)
    code_smell_score: Optional[float] = None   # 0-10
    missing_cases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "impl_maturity": self.impl_maturity,
            "has_tests": self.has_tests,
            "risk_level": self.risk_level,
            "issues": self.issues,
            "suggested_actions": self.suggested_actions,
            "code_smell_score": self.code_smell_score,
            "missing_cases": self.missing_cases,
        }


@dataclass
class GapContext:
    """传给评估器的 gap 上下文信息。"""
    id: str
    title: str
    description: str
    category: str
    priority: int
    blueprint_clause: Optional[Dict[str, Any]] = None
    related_files: List[str] = field(default_factory=list)


class GapQualityEvaluator:
    """
    利用 gemini/codex CLI 对 gap 对应的代码实现做一次“深度 code review + 风险评估”。
    """
    def __init__(
        self,
        gemini_cmd: str = "gemini",
        max_file_chars: int = 10_000,
    ) -> None:
        self.gemini_cmd = gemini_cmd
        self.max_file_chars = max_file_chars

    def evaluate_gap(
        self,
        gap_ctx: GapContext,
        snapshot: Optional[StatusSnapshot] = None,
    ) -> GapQualityScore:
        trace.record_event(
            event_type="gap_quality_start",
            payload={"gap_id": gap_ctx.id, "category": gap_ctx.category},
        )
        source_bundle = self._collect_source_bundle(gap_ctx)
        runtime_summary = self._build_runtime_summary(gap_ctx, snapshot)
        prompt = self._build_review_prompt(gap_ctx, source_bundle, runtime_summary)
        raw = self._call_gemini_cli(prompt)
        score = self._parse_quality_json(raw)
        trace.record_event(
            event_type="gap_quality_done",
            payload={"gap_id": gap_ctx.id, "score": score.to_dict()},
        )
        return score

    def _collect_source_bundle(self, gap_ctx: GapContext) -> str:
        chunks: List[str] = []
        for path in gap_ctx.related_files:
            p = Path(path)
            if not p.exists():
                continue
            try:
                text = p.read_text(encoding="utf-8")
                if len(text) > self.max_file_chars:
                    text = text[: self.max_file_chars] + "\n# ...(truncated)...\n"
                chunks.append(f"=== FILE: {path} ===\n{text}\n")
            except Exception:
                continue
        return "\n\n".join(chunks) if chunks else "[NO_SOURCE_FOUND]"

    def _build_runtime_summary(
        self,
        gap_ctx: GapContext,
        snapshot: Optional[StatusSnapshot],
    ) -> str:
        if snapshot is None:
            return "[NO_RUNTIME_STATS]"
        total = snapshot.task_stats_overall.total
        fail_rate = snapshot.task_stats_overall.fail_rate
        # recent_errors = getattr(snapshot, "recent_errors", [])[:10] # Assuming recent_errors doesn't exist
        parts = [f"Total tasks in last window: {total}", f"Overall fail rate: {fail_rate:.3f}"]
        return "\n".join(parts)

    def _build_review_prompt(self, gap_ctx: GapContext, source_bundle: str, runtime_summary: str) -> str:
        clause_block = json.dumps(gap_ctx.blueprint_clause, ensure_ascii=False, indent=2) if gap_ctx.blueprint_clause else "[NO_CLAUSE_STRUCT]"
        return f"""
你是一个专业的软件架构师 + 代码审查专家，熟悉自我迭代的 Meta-Agent 系统。
...
# 输出格式（非常重要）：
只能输出 **一个 JSON 对象**，不能包含其他任何文字。
...""" # Abridged for brevity

    def _call_gemini_cli(self, prompt: str) -> str:
        try:
            # Assuming gemini chat command; this will need adjustment for a real CLI
            proc = subprocess.run([self.gemini_cmd, "chat", "--prompt", prompt], text=True, capture_output=True, check=False)
        except Exception as e:
            logger.exception("Failed to invoke gemini cli")
            raise RuntimeError(f"gemini cli error: {e}") from e
        if proc.returncode != 0:
            logger.error("gemini cli exit %s, stderr=%s", proc.returncode, proc.stderr)
            raise RuntimeError(f"gemini cli non-zero exit: {proc.stderr}")
        return proc.stdout.strip()

    def _parse_quality_json(self, raw: str) -> GapQualityScore:
        try:
            data = json.loads(raw)
        except Exception:
            logger.warning("Failed to parse gap quality JSON, raw=%r", raw[:4000])
            return GapQualityScore(overall_score=5.0, impl_maturity="draft", has_tests=False, risk_level="medium", issues=["failed_to_parse_gap_quality_json"], suggested_actions=["manually review this module"])
        
        return GapQualityScore(
            overall_score=float(data.get("overall_score", 5.0)),
            impl_maturity=str(data.get("impl_maturity", "draft")),
            has_tests=bool(data.get("has_tests", False)),
            risk_level=str(data.get("risk_level", "medium")),
            issues=list(data.get("issues", [])),
            suggested_actions=list(data.get("suggested_actions", [])),
            code_smell_score=(float(data["code_smell_score"]) if "code_smell_score" in data else None),
            missing_cases=list(data.get("missing_cases", []))
        )
