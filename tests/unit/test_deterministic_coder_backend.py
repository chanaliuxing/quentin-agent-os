from __future__ import annotations

import json


def test_deterministic_coder_backend_emits_valid_payload() -> None:
    from meta_agent.tools.coder.deterministic_backend import DeterministicCoderBackend
    from meta_agent.tools.coder.base import CodeGenerationRequest

    backend = DeterministicCoderBackend()
    res = backend.generate(
        CodeGenerationRequest(
            goal="Add a deterministic marker",
            context_files=[],
            instructions="Return JSON with implementation_code and verification_test_code",
            request_tests=True,
        )
    )
    assert res.success is True
    payload = json.loads(res.code)
    assert "implementation_code" in payload
    assert "verification_test_code" in payload
    assert "def deterministic_backend_note" in payload["implementation_code"]

