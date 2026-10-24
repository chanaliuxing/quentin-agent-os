#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" && -x "./.venv/bin/python" ]]; then
  PYTHON_BIN="./.venv/bin/python"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python"
fi
PYTEST_BIN="${PYTEST_BIN:-}"
if [[ -z "$PYTEST_BIN" && -x "./.venv/bin/pytest" ]]; then
  PYTEST_BIN="./.venv/bin/pytest"
fi
if [[ -z "$PYTEST_BIN" ]]; then
  PYTEST_BIN="pytest"
fi

"$PYTEST_BIN" tests/unit/test_output_contracts.py -q
"$PYTEST_BIN" tests/unit/test_auto_review_default_flow.py -q
"$PYTEST_BIN" tests/unit/test_generate_phase_tasks_contracts.py tests/unit/test_human_review_queue.py -q
"$PYTEST_BIN" tests/replay/test_auto_review_replay_pack.py -q
"$PYTEST_BIN" -q
bash scripts/ci_control_plane_gate.sh
