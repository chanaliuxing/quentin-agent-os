#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

MODE="${1:-smoke}"
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

run_smoke() {
  "$PYTEST_BIN" \
    tests/unit/test_shutdown_terminal_events.py \
    tests/unit/test_terminal_state_consistency_matrix.py \
    tests/unit/test_recovery_recommendation.py \
    -q
  "$PYTHON_BIN" scripts/run_control_plane_matrix.py >/dev/null
  "$PYTHON_BIN" scripts/run_control_plane_slo.py >/dev/null
}

run_extended() {
  run_smoke

  run_id_int="reg-int-$(date +%s)"
  run_id_term="reg-term-$(( $(date +%s) + 1 ))"

  "$PYTHON_BIN" scripts/run_temporal_with_shutdown.py --project-id "$run_id_int" --prd-path ./blueprint.md >/tmp/"$run_id_int".log 2>&1 &
  pid_int=$!
  sleep 8
  if kill -0 "$pid_int" 2>/dev/null; then
    kill -INT "$pid_int" || true
  fi
  wait "$pid_int" || true

  "$PYTHON_BIN" scripts/run_temporal_with_shutdown.py --project-id "$run_id_term" --prd-path ./blueprint.md >/tmp/"$run_id_term".log 2>&1 &
  pid_term=$!
  sleep 8
  if kill -0 "$pid_term" 2>/dev/null; then
    kill -TERM "$pid_term" || true
  fi
  wait "$pid_term" || true

  "$PYTHON_BIN" - "$run_id_int" "$run_id_term" <<'PY'
import json
import sys
from pathlib import Path

run_id_int = sys.argv[1]
run_id_term = sys.argv[2]
root = Path(".")
event_root = root / "runtime" / "event_log"
for run_id in (run_id_int, run_id_term):
    event_file = event_root / run_id / "phase_01" / "events.jsonl"
    summary_file = root / "runtime" / "evidence" / run_id / "phase_01" / "execution_summary.json"
    if not event_file.exists() or not summary_file.exists():
        raise SystemExit(f"missing artifacts for {run_id}")
    events = [json.loads(line) for line in event_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not any(str(item.get("event_type", "")).strip() == "WORKFLOW_TERMINATED" for item in events):
        raise SystemExit(f"missing WORKFLOW_TERMINATED for {run_id}")
PY

  "$PYTHON_BIN" scripts/run_control_plane_slo.py >/dev/null
}

if [[ "$MODE" == "smoke" ]]; then
  run_smoke
elif [[ "$MODE" == "extended" ]]; then
  run_extended
else
  echo "usage: $0 [smoke|extended]"
  exit 1
fi

echo "control plane regression ($MODE) passed"
