from __future__ import annotations

from quentin.runtime.silent_protocol import SILENT_REPLY_TOKEN, is_silent_reply


def test_silent_reply_is_intercepted() -> None:
    assert is_silent_reply(SILENT_REPLY_TOKEN) is True
    assert is_silent_reply(f"  {SILENT_REPLY_TOKEN}  ") is True


def test_non_silent_reply_not_intercepted() -> None:
    assert is_silent_reply("") is False
    assert is_silent_reply("ok") is False
    assert is_silent_reply("[SILENT] extra") is False

