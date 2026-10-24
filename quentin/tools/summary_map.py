from __future__ import annotations

from typing import Dict, Iterable, List, Optional


def _clean(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _truncate_words(text: str, max_words: int = 10) -> str:
    cleaned = _clean(text)
    if not cleaned:
        return ""
    words = cleaned.split(" ")
    if len(words) <= max_words:
        return cleaned
    return " ".join(words[:max_words]).strip() + "..."


def build_tool_summary_map(
    *,
    tool_descriptions: Dict[str, str],
    max_words: int = 10,
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name in sorted(tool_descriptions.keys()):
        desc = _truncate_words(tool_descriptions.get(name, ""), max_words=max_words)
        out[str(name)] = desc or "tool available"
    return out


def format_tool_summary_block(summary_map: Dict[str, str]) -> str:
    if not summary_map:
        return ""
    lines: List[str] = [
        "TOOLS (short summaries):",
    ]
    for name in sorted(summary_map.keys()):
        lines.append(f"- {name}: {summary_map[name]}")
    lines.append("If detailed parameters are needed, call help(tool='<tool_name>').")
    return "\n".join(lines)

