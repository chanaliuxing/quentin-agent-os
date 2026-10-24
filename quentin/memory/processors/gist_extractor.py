from __future__ import annotations

from typing import Iterable, List


def extract_gist_rules(texts: Iterable[str], *, max_rules: int = 8) -> List[str]:
    """
    v0 gist extraction: heuristic, conservative, cheap.

    The goal is to produce reusable skeleton rules (not detailed traces) to avoid memory bloat.
    """
    joined = "\n".join([str(t or "") for t in texts if str(t or "").strip()])[:20000].lower()
    rules: List[str] = []

    def add(rule: str) -> None:
        r = str(rule or "").strip()
        if not r:
            return
        if r not in rules:
            rules.append(r)

    if "tool_not_found" in joined or "tool not found" in joined:
        add("When a tool is missing, list available tools and verify the exact tool name before retrying.")
    if "permission denied" in joined or "forbidden" in joined or "unauthorized" in joined:
        add("If permission is denied, check SafetyKernel/tool policy and switch to a lower-risk path or request approval.")
    if "file not found" in joined or "no such file" in joined:
        add("If a file path is missing, run discovery (ls/rg) to confirm the real path before editing.")
    if "invalid json" in joined or "jsondecodeerror" in joined:
        add("If JSON parsing fails, strip code fences and re-parse; otherwise fall back to a minimal schema-safe envelope.")
    if "timeout" in joined:
        add("If a step times out, reduce scope, add a smaller probe, or retry with a longer timeout only after verifying progress.")
    if "repeated_tool_call_loop" in joined or "no user-visible progress" in joined:
        add("If tool calls repeat with no progress, summarize current state, change strategy, or fall back to planner reflection.")

    # Always include a generic safe execution rule.
    add("Prefer deterministic, low-risk discovery steps before any write/delete/install action.")

    return rules[: max(1, int(max_rules))]

