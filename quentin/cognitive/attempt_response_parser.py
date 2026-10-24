from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict
from quentin.cognitive.xml_integrity import repair_structured_response


@dataclass
class ParsedModelResponse:
    think: str = ""
    final: str = ""
    cleaned: str = ""
    has_structured_tags: bool = False
    repetition_detected: bool = False
    xml_repair_applied: bool = False
    xml_repair_mode: str = "none"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _extract_tag_block(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    return _clean_text(m.group(1))


def _extract_thinking_block(text: str) -> str:
    think = _extract_tag_block(text, "think")
    if think:
        return think
    return _extract_tag_block(text, "thinking")


def detect_repetition(text: str) -> bool:
    content = str(text or "").strip()
    if not content:
        return False
    lines = [ln.strip().lower() for ln in content.splitlines() if ln.strip()]
    if len(lines) >= 4:
        counts: Dict[str, int] = {}
        for ln in lines:
            counts[ln] = counts.get(ln, 0) + 1
        max_repeat = max(counts.values()) if counts else 1
        if max_repeat >= 3 and (max_repeat / max(1, len(lines))) >= 0.5:
            return True

    normalized = _clean_text(content).lower()
    # Repeated phrase/segment heuristic.
    if re.search(r"(.{12,80})\1\1", normalized):
        return True
    return False


def parse_model_response_text(text: str) -> ParsedModelResponse:
    raw, repair_report = repair_structured_response(str(text or ""))
    think = _extract_thinking_block(raw)
    final = _extract_tag_block(raw, "final")
    has_tags = bool(think or final)

    cleaned = raw
    if has_tags:
        cleaned = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<final>.*?</final>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = _clean_text(cleaned)

    chosen_final = final or cleaned
    if not final:
        m_fence = re.search(r"```(?:json|xml)?\s*(.*?)\s*```", raw, re.IGNORECASE | re.DOTALL)
        if m_fence:
            fenced = _clean_text(m_fence.group(1))
            if fenced:
                chosen_final = fenced
    repetition = detect_repetition(chosen_final)
    return ParsedModelResponse(
        think=think,
        final=chosen_final,
        cleaned=cleaned,
        has_structured_tags=has_tags,
        repetition_detected=repetition,
        xml_repair_applied=bool(repair_report.get("applied", False)),
        xml_repair_mode=str(repair_report.get("mode") or "none"),
    )
