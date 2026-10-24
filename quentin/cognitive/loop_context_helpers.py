from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from quentin.infra.text.head_tail import truncate_head_tail


def _extract_explicit_task_paths(*, repo_root: Path, task_text: str) -> List[str]:
    raw = str(task_text or "")
    candidates: List[str] = []
    patterns = [
        r"`([^`\n]+)`",
        r"'([^'\n]+)'",
        r"\"([^\"\n]+)\"",
        r"(?<![\w/.-])(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, raw):
            value = match if isinstance(match, str) else ""
            norm = str(value or "").strip().strip("/")
            if norm:
                candidates.append(norm)

    seen: set[str] = set()
    existing: List[str] = []
    missing: List[str] = []
    for rel in candidates:
        key = rel.lower()
        if key in seen:
            continue
        seen.add(key)
        p = (repo_root / rel).resolve()
        try:
            p.relative_to(repo_root)
        except Exception:
            continue
        rel_norm = str(p.relative_to(repo_root))
        if p.exists():
            existing.append(rel_norm)
        else:
            missing.append(rel_norm)
    return existing + missing


def generate_sensing_report(*, repo_root: Path, task: Any, focus_paths: List[str]) -> Dict[str, Any]:
    """Generate a structured pre-sensing report for planner context."""
    task_text = str(getattr(task, "input_text", "") or "").lower()
    keywords = sorted({k for k in re.findall(r"[a-z0-9_]{4,}", task_text) if k not in {"this", "that", "with", "from"}})
    keywords = keywords[:8]
    policy_summary: Any = {}
    try:
        from quentin.cognitive.perception.policy_provider import PolicyPerceptionProvider

        policy_summary = PolicyPerceptionProvider(repo_root=repo_root).get_policy_summary()
    except Exception:
        policy_summary = {}
    if not isinstance(policy_summary, dict):
        policy_summary = {}
    if "allowed_write_roots" not in policy_summary:
        try:
            from quentin.kernel.path_guard import PathGuard

            allowed = PathGuard(repo_root.resolve(), allowed_roots=None).allowed_roots
            policy_summary["allowed_write_roots"] = [str(x) for x in allowed]
        except Exception:
            policy_summary["allowed_write_roots"] = []
    report = {
        "system_policies": policy_summary,
        "focus_paths": focus_paths,
        "keywords": keywords,
        "evidence": [],
    }

    for rel_path in focus_paths:
        full_path = repo_root / rel_path
        evidence_item = {
            "path": rel_path,
            "exists": full_path.exists(),
            "is_dir": full_path.is_dir() if full_path.exists() else False,
        }

        if full_path.exists():
            if full_path.is_file():
                try:
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    evidence_item["hash"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    if rel_path.endswith((".yaml", ".yml", ".py", ".json", ".md")):
                        evidence_item["snippet"] = truncate_head_tail(content, max_chars=4000)
                    
                    # P0: Functional Validation (Pre-sensing Hardening)
                    f_check = {"status": "skipped"}
                    if rel_path.endswith(".py"):
                        import py_compile
                        import tempfile
                        with tempfile.NamedTemporaryFile(suffix=".py", delete=True) as tmp:
                            tmp.write(content.encode("utf-8"))
                            tmp.flush()
                            try:
                                py_compile.compile(tmp.name, doraise=True)
                                f_check = {"status": "pass", "type": "syntax_check"}
                            except Exception as pe:
                                f_check = {"status": "fail", "type": "syntax_check", "error": str(pe)}
                    elif rel_path.endswith(("manifest.yaml", "manifest.yml")):
                        import yaml
                        try:
                            data = yaml.safe_load(content) or {}
                            # Aligned with action layer (filesystem.py) to prevent already_done hallucinations
                            required = ["id", "name", "description", "entrypoint", "kind", "domain", "risk_level", "output_trust", "permissions"]
                            missing = [k for k in required if k not in data]
                            if missing:
                                f_check = {"status": "fail", "type": "manifest_keys", "error": f"missing keys: {missing}"}
                            else:
                                f_check = {"status": "pass", "type": "manifest_keys"}
                        except Exception as ye:
                            f_check = {"status": "fail", "type": "manifest_parse", "error": str(ye)}
                    evidence_item["functional_check"] = f_check

                except Exception as e:
                    evidence_item["error"] = str(e)
            elif full_path.is_dir():
                try:
                    items = os.listdir(str(full_path))
                    items_sorted = sorted(items)
                    head = items_sorted[:50]
                    evidence_item["contents_head"] = head
                    evidence_item["contents_total"] = len(items_sorted)
                    if len(items_sorted) > 50:
                        evidence_item["contents_head"].append("...")

                    if keywords:
                        matches = [x for x in items_sorted if any(k in x.lower() for k in keywords)]
                        evidence_item["contents_matches"] = matches[:50]
                        if len(matches) > 50:
                            evidence_item["contents_matches"].append("...")

                    if rel_path.replace("\\", "/").rstrip("/") == "extensions/tools" and keywords:
                        implied = []
                        if "gemini_cli" in keywords or "gemini" in keywords:
                            implied.append("gemini_cli")
                        implied = implied[:5]
                        probes = []
                        for name in implied:
                            child_dir = full_path / name
                            probes.append({"name": name, "exists": child_dir.exists(), "is_dir": child_dir.is_dir() if child_dir.exists() else False})
                            manifest = child_dir / "manifest.yaml"
                            logic = child_dir / "logic.py"
                            probes.append({"name": f"{name}/manifest.yaml", "exists": manifest.exists(), "is_file": manifest.is_file() if manifest.exists() else False})
                            probes.append({"name": f"{name}/logic.py", "exists": logic.exists(), "is_file": logic.is_file() if logic.exists() else False})
                        if probes:
                            evidence_item["expected_children"] = probes
                except Exception as e:
                    evidence_item["error"] = str(e)

        report["evidence"].append(evidence_item)

    return report


def compact_last_execution_for_planner(last_exec_result: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact planner-facing digest from previous executor result."""
    if not isinstance(last_exec_result, dict) or not last_exec_result:
        return {}
    raw = last_exec_result.get("raw") if isinstance(last_exec_result.get("raw"), dict) else {}
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    tool_summaries: List[Dict[str, Any]] = []
    for s in steps[-6:]:
        if not isinstance(s, dict):
            continue
        tool = None
        args = None
        try:
            result = s.get("result") if isinstance(s.get("result"), dict) else {}
            call_tool = result.get("call_tool") if isinstance(result.get("call_tool"), dict) else None
            if call_tool:
                tool = call_tool.get("name")
                args = call_tool.get("arguments")
        except Exception:
            tool = None
            args = None
        tool_summaries.append(
            {
                "step_id": s.get("step_id"),
                "ok": bool(s.get("success", True)) and not bool(s.get("error")),
                "tool": tool,
                "args": args,
                "error": s.get("error"),
            }
        )
    final_output = str(last_exec_result.get("final_output") or "")
    actions_summary = str(last_exec_result.get("actions_summary") or "")
    return {
        "final_output_preview": final_output[:800],
        "actions_summary_preview": actions_summary[:1200],
        "recent_tools": tool_summaries,
        "is_system_error": bool(last_exec_result.get("is_system_error", False)),
        "attempt_evaluation": last_exec_result.get("attempt_evaluation") if isinstance(last_exec_result.get("attempt_evaluation"), dict) else {},
    }


def get_candidate_files(*, repo_root: Path, task_text: str, max_files: int = 12) -> List[str]:
    """Heuristic candidate file ranking for planner hints."""
    text = str(task_text or "").strip().lower()
    explicit = _extract_explicit_task_paths(repo_root=repo_root, task_text=task_text)
    if not text:
        return explicit[:max_files]
    terms = [
        term
        for term in re.findall(r"[a-zA-Z_]{3,}", text)
        if term not in {"with", "from", "this", "that", "your", "have", "should", "need", "make"}
    ]
    if not terms:
        return explicit[:max_files]

    ignore_dirs = {".git", "__pycache__", "venv", ".venv", ".pytest_cache", "node_modules", "data", "logs"}
    candidates: List[tuple[int, str]] = []
    scanned = 0
    for path in repo_root.rglob("*.py"):
        if any(part in ignore_dirs for part in path.parts):
            continue
        scanned += 1
        if scanned > 3000:
            break
        rel = str(path.relative_to(repo_root))
        rel_lower = rel.lower()
        score = 0
        for term in terms[:8]:
            if term in rel_lower:
                score += 3
        if score == 0:
            continue
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:1200].lower()
            for term in terms[:5]:
                if term in head:
                    score += 1
        except Exception:
            pass
        if score > 0:
            candidates.append((score, rel))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    out: List[str] = []
    seen: set[str] = set()
    for path in explicit + [p for _, p in candidates]:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(str(path))
        if len(out) >= max_files:
            break
    return out
