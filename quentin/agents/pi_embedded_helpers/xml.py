from __future__ import annotations

import re


def enforce_closed_tag_blocks(text: str, *, tags: tuple[str, ...] = ("final", "think")) -> str:
    s = str(text or "")
    out = s
    for tag in tags:
        open_pat = re.compile(rf"<{tag}\b[^>]*>", re.IGNORECASE)
        close_pat = re.compile(rf"</{tag}>", re.IGNORECASE)
        opens = len(open_pat.findall(out))
        closes = len(close_pat.findall(out))
        if opens > closes:
            out += f"</{tag}>"
    return out

