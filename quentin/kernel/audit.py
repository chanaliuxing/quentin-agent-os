from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional

from quentin.runtime.session_write_lock import acquire_session_write_lock
from quentin.config.feature_flags import feature_flags


@dataclass
class AuditEvent:
    action_id: str
    event_type: str
    phase: str
    actor: str
    timestamp: float = field(default_factory=lambda: time.time())
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuditLogger:
    def __init__(self, *, repo_root: str | Path = ".", path: str | Path = "data/audit_events.jsonl") -> None:
        import os
        self.repo_root = Path(repo_root).resolve()
        override = (os.getenv("QUENTIN_AUDIT_PATH") or "").strip()
        if override:
            p = Path(override).expanduser()
            if not p.is_absolute():
                p = (self.repo_root / p).resolve()
            self.path = p
        else:
            self.path = (self.repo_root / path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        
        # P3-Audit: Security-specific log
        self.security_path = (self.repo_root / "data" / "security_audit.jsonl").resolve()

    def append(self, event: Any) -> None:
        # P3-Audit integration: check if it's the new schema or old
        is_security = False
        if hasattr(event, "event_id") and hasattr(event, "decision"):
            is_security = True
        
        record = event.to_dict() if hasattr(event, "to_dict") else asdict(event)
        
        # Log to main audit
        self._write(self.path, record)
        
        # P3-Audit: Log to security audit if flag enabled
        if is_security and feature_flags.p3_audit_v1:
            self._write(self.security_path, record)

    def _write(self, path: Path, record: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = acquire_session_write_lock(session_file=path)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            lock["release"]()


_DEFAULT_LOGGER: Optional[AuditLogger] = None


def default_audit_logger() -> AuditLogger:
    global _DEFAULT_LOGGER
    if _DEFAULT_LOGGER is None:
        _DEFAULT_LOGGER = AuditLogger()
    return _DEFAULT_LOGGER
