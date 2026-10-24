import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(
    os.getenv("REAL_LLM_SMOKE") not in ("1", "true", "yes"),
    reason="Real LLM smoke test requires REAL_LLM_SMOKE=1 and provider credentials in env.",
)
def test_real_llm_smoke_script_runs():
    # This test intentionally performs a real external call when enabled.
    # It must be opt-in to keep CI/offline runs stable.
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_real_llm_smoke.py",
            "--prompt",
            "Say 'pong' only.",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "LLM_STUB": "0"},
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip(), "expected non-empty output"

