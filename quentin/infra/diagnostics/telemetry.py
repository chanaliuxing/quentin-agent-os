from __future__ import annotations

import time
import uuid
import logging
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from quentin.infra.canvas.broadcaster import broadcaster

logger = logging.getLogger(__name__)

@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_id: Optional[str]
    name: str
    start_time: float
    end_time: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    status: str = "ok"

class TelemetryRecorder:
    """
    OpenTelemetry-style diagnostics recorder.
    Broadcasts spans to Canvas for real-time visualization.
    """
    def __init__(self):
        self._active_spans: Dict[str, Span] = {}

    def start_span(self, name: str, trace_id: Optional[str] = None, parent_id: Optional[str] = None, attributes: Dict = None) -> Span:
        trace_id = trace_id or uuid.uuid4().hex
        span_id = uuid.uuid4().hex
        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_id=parent_id,
            name=name,
            start_time=time.time(),
            attributes=attributes or {}
        )
        self._active_spans[span_id] = span
        return span

    async def end_span(self, span: Span, status: str = "ok", error: Optional[str] = None):
        span.end_time = time.time()
        span.status = status
        if error:
            span.attributes["error"] = str(error)
        
        if span.span_id in self._active_spans:
            del self._active_spans[span.span_id]

        # Log completion
        duration_ms = (span.end_time - span.start_time) * 1000
        logger.debug(f"Span finished: {span.name} ({duration_ms:.2f}ms) [{status}]")

        # Broadcast to Canvas
        await broadcaster.broadcast({
            "type": "telemetry_span",
            "payload": {
                "trace_id": span.trace_id,
                "span_id": span.span_id,
                "parent_id": span.parent_id,
                "name": span.name,
                "duration_ms": duration_ms,
                "status": status,
                "attributes": span.attributes
            }
        })

# Global instance
telemetry = TelemetryRecorder()
