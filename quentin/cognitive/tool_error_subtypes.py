from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _collect_error_text(last_exec_result: Dict[str, Any]) -> str:
    raw = last_exec_result.get("raw") if isinstance(last_exec_result.get("raw"), dict) else {}
    parts: List[str] = [str(raw.get("error") or ""), str(last_exec_result.get("error") or "")]
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    for s in steps:
        if not isinstance(s, dict):
            continue
        parts.append(str(s.get("error") or ""))
        res = s.get("result") if isinstance(s.get("result"), dict) else {}
        parts.append(str(res.get("error") or ""))
        parts.append(str(res.get("reason") or ""))
        tr = res.get("tool_result") if isinstance(res.get("tool_result"), dict) else {}
        parts.append(str(tr.get("error") or ""))
        feedback_tail = res.get("feedback_tail") if isinstance(res.get("feedback_tail"), list) else []
        for item in feedback_tail[-6:]:
            if not isinstance(item, dict):
                continue
            parts.append(str(item.get("type") or ""))
            parts.append(str(item.get("reason") or ""))
    return " | ".join(parts).lower()


def _infer_last_tool_family(last_exec_result: Dict[str, Any]) -> str:
    raw = last_exec_result.get("raw") if isinstance(last_exec_result.get("raw"), dict) else {}
    steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    for s in reversed(steps):
        if not isinstance(s, dict):
            continue
        res = s.get("result") if isinstance(s.get("result"), dict) else {}
        call_tool = res.get("call_tool") if isinstance(res.get("call_tool"), dict) else {}
        name = str(call_tool.get("tool_name") or "").strip().lower()
        if not name:
            continue
        if name.startswith("shell."):
            return "shell"
        if name.startswith("browser.") or name.startswith("web."):
            return "browser"
        if name.startswith("fs."):
            return "filesystem"
    return "generic"


def classify_tool_error_subtype(*, last_exec_result: Dict[str, Any]) -> Tuple[str, str]:
    text = _collect_error_text(last_exec_result)
    fam = _infer_last_tool_family(last_exec_result)

    if "plan_execution_misalignment" in text:
        return fam, "plan_execution_misalignment"

    if fam == "shell":
        if "permission denied" in text or "operation not permitted" in text:
            return fam, "shell_permission_denied"
        if "timeout" in text or "timed out" in text:
            return fam, "shell_timeout"
        if "not found" in text:
            return fam, "shell_command_not_found"
        return fam, "shell_generic_error"

    if fam == "browser":
        if "selector" in text and ("not found" in text or "no such element" in text):
            return fam, "browser_selector_not_found"
        if "navigation" in text and ("timeout" in text or "timed out" in text):
            return fam, "browser_navigation_timeout"
        if "detached" in text or "stale element" in text:
            return fam, "browser_stale_element"
        return fam, "browser_generic_error"

    if fam == "filesystem":
        if "permission denied" in text:
            return fam, "filesystem_permission_denied"
        if "not found" in text or "no such file" in text:
            return fam, "filesystem_path_not_found"
        if "validation" in text or "invalid" in text:
            return fam, "filesystem_validation_error"
        return fam, "filesystem_generic_error"

    if "timeout" in text or "timed out" in text:
        return fam, "generic_timeout"
    return fam, "generic_tool_error"
