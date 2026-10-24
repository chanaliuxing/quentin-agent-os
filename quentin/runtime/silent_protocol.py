from __future__ import annotations

SILENT_REPLY_TOKEN = "[[SILENT_REPLY]]"
SILENT_REPLY_ALIASES = {
    SILENT_REPLY_TOKEN.lower(),
    "[silent]".lower(),
    "[[silent]]".lower(),
    "[[silent_reply]]".lower(),
}


def is_silent_reply(text: str) -> bool:
    return str(text or "").strip().lower() in SILENT_REPLY_ALIASES
