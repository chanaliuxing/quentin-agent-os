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

"$PYTHON_BIN" scripts/run_business_failure_goldens.py
"$PYTHON_BIN" scripts/run_agent_execution_failure_breakdown.py --window-size 20
"$PYTHON_BIN" scripts/run_agent_execution_remediation.py --window-size 20 --min-count 2 --min-ratio 0.2
"$PYTHON_BIN" scripts/promote_business_taxonomy.py --window-size 20 --promote-count 2
"$PYTHON_BIN" scripts/run_business_failure_monitor.py --window-size 20 --min-count 2 --min-ratio 0.05
"$PYTHON_BIN" scripts/run_recovery_canary.py --window-size 50

# Optional subprocess-focused variant compare (quick operator lens).
# Enable by setting both VARIANT_A and VARIANT_B in environment.
if [[ -n "${VARIANT_A:-}" && -n "${VARIANT_B:-}" ]]; then
  "$PYTHON_BIN" scripts/compare_agent_variants.py \
    --variant-a "${VARIANT_A}" \
    --variant-b "${VARIANT_B}" \
    --match-mode "${VARIANT_MATCH_MODE:-prefix}" \
    --window-size "${VARIANT_WINDOW_SIZE:-50}" \
    --only-subprocess
fi
