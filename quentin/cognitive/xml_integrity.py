from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class XmlRepairReport:
    applied: bool = False
    mode: str = "none"
    dangling_head_trimmed: bool = False
    malformed_nesting_fixed: bool = False
    dropped_stray_closing_tags: int = 0
    auto_closed_tags: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _trim_dangling_tag_head(text: str) -> Tuple[str, bool]:
    raw = str(text or "")
    last_lt = raw.rfind("<")
    last_gt = raw.rfind(">")
    if last_lt >= 0 and last_lt > last_gt:
        return raw[:last_lt], True
    return raw, False


def _repair_known_tag_nesting(text: str, *, known_tags: List[str]) -> Tuple[str, XmlRepairReport]:
    report = XmlRepairReport(mode="xml_tag_balance")
    if not text:
        return "", report
    tag_set = {str(t).strip().lower() for t in (known_tags or []) if str(t).strip()}
    if not tag_set:
        return text, report

    token_re = re.compile(r"</?([A-Za-z][A-Za-z0-9_-]*)(?:\s[^>]*)?>", re.IGNORECASE)
    out: List[str] = []
    stack: List[str] = []
    pos = 0
    for m in token_re.finditer(text):
        out.append(text[pos:m.start()])
        full = m.group(0)
        name = str(m.group(1) or "").strip().lower()
        is_close = full.startswith("</")
        if name not in tag_set:
            out.append(full)
        elif not is_close:
            stack.append(name)
            out.append(f"<{name}>")
        else:
            if name in stack:
                while stack and stack[-1] != name:
                    report.malformed_nesting_fixed = True
                    out.append(f"</{stack.pop()}>")
                    report.auto_closed_tags += 1
                if stack and stack[-1] == name:
                    stack.pop()
                    out.append(f"</{name}>")
            else:
                report.dropped_stray_closing_tags += 1
        pos = m.end()
    out.append(text[pos:])
    while stack:
        out.append(f"</{stack.pop()}>")
        report.auto_closed_tags += 1
    repaired = "".join(out)
    report.applied = bool(
        report.dangling_head_trimmed
        or report.malformed_nesting_fixed
        or report.dropped_stray_closing_tags > 0
        or report.auto_closed_tags > 0
    )
    return repaired, report


def repair_structured_response(
    text: str,
    *,
    known_tags: List[str] | None = None,
) -> Tuple[str, Dict[str, Any]]:
    raw = str(text or "")
    tags = known_tags or ["think", "final", "answer"]
    trimmed, trimmed_flag = _trim_dangling_tag_head(raw)
    repaired, report = _repair_known_tag_nesting(trimmed, known_tags=tags)
    report.dangling_head_trimmed = bool(trimmed_flag)
    report.applied = bool(
        report.dangling_head_trimmed
        or report.malformed_nesting_fixed
        or report.dropped_stray_closing_tags > 0
        or report.auto_closed_tags > 0
    )
    return repaired, report.to_dict()


def repair_unclosed_xml_tags(text: str, *, known_tags: List[str] | None = None) -> str:
    repaired, _ = repair_structured_response(text, known_tags=known_tags)
    return repaired
