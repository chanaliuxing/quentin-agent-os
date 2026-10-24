from __future__ import annotations

from typing import Iterable, Optional


def _clean(v: Optional[str]) -> str:
    text = str(v or "").strip()
    return text


def _join_hints(hints: Optional[Iterable[str]]) -> str:
    if hints is None:
        return ""
    out = []
    for item in hints:
        text = _clean(str(item or ""))
        if text:
            out.append(text)
    return "\n".join(out).strip()


def build_layered_system_prompt(
    *,
    base_system: str,
    soul: str = "",
    skill: str = "",
    project_context: str = "",
    hints: Optional[Iterable[str]] = None,
) -> str:
    """
    Build a deterministic prompt stack:
    SOUL > SKILL > PROJECT_CONTEXT > HINTS.
    """
    sections = []
    base = _clean(base_system)
    if base:
        sections.append(base)

    soul_text = _clean(soul)
    if soul_text:
        sections.append("SOUL (highest priority):\n" + soul_text)

    skill_text = _clean(skill)
    if skill_text:
        sections.append("SKILL CONTEXT:\n" + skill_text)

    context_text = _clean(project_context)
    if context_text:
        sections.append("PROJECT CONTEXT:\n" + context_text)

    hint_text = _join_hints(hints)
    if hint_text:
        sections.append(
            "RUNTIME HINTS (lowest priority; do not override SOUL/SKILL constraints):\n" + hint_text
        )

    return "\n\n".join(sections).strip()

