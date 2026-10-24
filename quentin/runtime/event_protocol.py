from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from quentin.runtime.stream_protocol import StreamOutput


@dataclass
class EventProtocol:
    queue: Any
    source: str = "cognitive_loop"

    def emit_message_stream(
        self,
        *,
        session_id: str,
        turn_id: str,
        stream: StreamOutput,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.queue is None:
            return
        sid = str(session_id or "global")
        tid = str(turn_id or "")
        payload_meta = dict(meta or {})

        total = len(stream.chunks)
        for idx, chunk in enumerate(stream.chunks, start=1):
            self.queue.emit_brain_event(
                session_id=sid,
                event_type="message.delta",
                category="message",
                phase="delta",
                source=self.source,
                turn_id=tid,
                payload={
                    "chunk": chunk,
                    "chunk_index": idx,
                    "chunk_total": total,
                    "is_final_chunk": idx == total,
                    "reply_id": stream.directives.reply_id or "",
                },
            )

        self.queue.emit_brain_event(
            session_id=sid,
            event_type="message.final",
            category="message",
            phase="final",
            source=self.source,
            turn_id=tid,
            payload={
                "text": stream.visible_text,
                "reply_id": stream.directives.reply_id or "",
                "media": list(stream.directives.media or []),
                "silent": bool(stream.directives.silent),
                "has_hidden_thinking": bool(stream.hidden_thinking),
                "meta": payload_meta,
            },
        )
