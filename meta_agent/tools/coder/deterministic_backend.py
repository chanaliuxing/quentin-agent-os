from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from meta_agent.tools.coder.base import CoderBackend, CodeGenerationRequest, CodeGenerationResult


class DeterministicCoderBackend(CoderBackend):
    """
    Deterministic, offline coder backend (no external LLM/CLI).

    Purpose:
    - CI / local regression runs where external model providers are disabled.
    - Provide a schema-valid response that unblocks the self-programming pipeline.

    Notes:
    - This backend does NOT attempt real implementation. It emits a harmless module with
      a stable marker plus a trivial pytest test. It is intended as a safety valve and
      a reproducible baseline.
    """

    name: str = "deterministic"

    def generate(self, req: CodeGenerationRequest) -> CodeGenerationResult:
        # Keep goal printable and filesystem-safe without relying on a brittle character range.
        safe_goal = re.sub(r"[^0-9A-Za-z _:/\\\\-]+", "", str(req.goal or "")).strip()
        ts = datetime.now(timezone.utc).isoformat()

        implementation_code = (
            '"""Deterministic self-programming stub (offline backend).\n'
            f"GeneratedAtUTC: {ts}\n"
            f"Goal: {safe_goal}\n"
            '"""\n\n'
            "from __future__ import annotations\n\n"
            "DETERMINISTIC_BACKEND_MARKER = True\n\n"
            "def deterministic_backend_note() -> str:\n"
            f"    return {json.dumps(safe_goal)}\n"
        )

        verification_test_code = (
            '"""Deterministic smoke test for offline self-programming backend."""\n\n'
            "def test_deterministic_backend_smoke() -> None:\n"
            "    assert True\n"
        )

        payload = {
            "implementation_code": implementation_code,
            "verification_test_code": verification_test_code,
        }

        return CodeGenerationResult(
            success=True,
            code=json.dumps(payload, ensure_ascii=False),
            reasoning="deterministic_backend_offline_stub",
            raw_output=None,
            test_code=verification_test_code,
        )
