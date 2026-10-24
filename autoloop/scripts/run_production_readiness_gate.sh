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

PRD_PATH="${PRD_PATH:-./blueprint.md}"
CANARY_RUNS="${CANARY_RUNS:-3}"
CANARY_TIMEOUT_PROFILE="${CANARY_TIMEOUT_PROFILE:-codex_balanced}"
CANARY_RUN_TIMEOUT_SECONDS="${CANARY_RUN_TIMEOUT_SECONDS:-300}"
CANARY_MAX_GLOBAL_TIMEOUT_RATE="${CANARY_MAX_GLOBAL_TIMEOUT_RATE:-0.0}"
CANARY_MAX_DEGRADED_RUN_RATE="${CANARY_MAX_DEGRADED_RUN_RATE:-0.0}"
CANARY_OUT="${CANARY_OUT:-runtime/metrics/codex_timeout_canary_report_production_readiness.json}"

echo "[1/3] Running control-plane gate..."
bash scripts/ci_control_plane_gate.sh

echo "[2/3] Running codex canary..."
if ! AGENT_RUNNER_TYPE=codex "$PYTHON_BIN" scripts/run_codex_timeout_canary.py \
  --prd-path "$PRD_PATH" \
  --runs "$CANARY_RUNS" \
  --timeout-profile "$CANARY_TIMEOUT_PROFILE" \
  --run-timeout-seconds "$CANARY_RUN_TIMEOUT_SECONDS" \
  --max-global-timeout-rate "$CANARY_MAX_GLOBAL_TIMEOUT_RATE" \
  --max-degraded-run-rate "$CANARY_MAX_DEGRADED_RUN_RATE" \
  --enforce-promotion-gate \
  --out "$CANARY_OUT"; then
  echo "codex canary failed; dump quick summary:"
  "$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path

root = Path(".")
canary_out = os.environ.get(
    "CANARY_OUT",
    "runtime/metrics/codex_timeout_canary_report_production_readiness.json",
)
path = root / canary_out
if not path.exists():
    raise SystemExit("missing canary report")
payload = json.loads(path.read_text(encoding="utf-8"))
print("promotion_eligible:", payload.get("promotion_eligible"))
print("gate_reasons:", payload.get("gate_reasons", []))
print("terminal_distribution:", payload.get("terminal_distribution", {}))
print("primary_failure_distribution:", payload.get("primary_failure_distribution", {}))
print("degraded_breakdown:", payload.get("degraded_breakdown", {}))
PY
  exit 1
fi

echo "[3/3] Validating reliability + detail coverage..."
"$PYTHON_BIN" - <<'PY'
import json
import os
from pathlib import Path

root = Path(".")
slo_path = root / "runtime" / "metrics" / "control_plane_slo_report.json"
canary_out = os.environ.get(
    "CANARY_OUT",
    "runtime/metrics/codex_timeout_canary_report_production_readiness.json",
)
canary_path = root / canary_out

if not slo_path.exists():
    raise SystemExit("missing control_plane_slo_report.json")
if not canary_path.exists():
    raise SystemExit("missing codex_timeout_canary_report_production_readiness.json")

slo = json.loads(slo_path.read_text(encoding="utf-8"))
metrics = dict(slo.get("metrics", {}) or {})
required_detail_missing = float(metrics.get("required_test_failure_detail_missing_rate", 1.0))
if required_detail_missing > 0.0:
    raise SystemExit(
        f"required_test_failure_detail_missing_rate not ready: {required_detail_missing}"
    )

canary = json.loads(canary_path.read_text(encoding="utf-8"))
if not bool(canary.get("promotion_eligible", False)):
    raise SystemExit(
        f"canary promotion blocked: {canary.get('gate_reasons', [])}"
    )

breakdown = dict(canary.get("degraded_breakdown", {}) or {})
reliability_rate = float(breakdown.get("reliability_degraded_run_rate", 1.0))
if reliability_rate > 0.0:
    raise SystemExit(
        f"reliability_degraded_run_rate not ready: {reliability_rate}"
    )

print("production readiness gate passed")
PY

echo "[4/4] Running execution remediation monitor..."
"$PYTHON_BIN" scripts/run_agent_execution_remediation.py \
  --window-size "${EXECUTION_REMEDIATION_WINDOW_SIZE:-20}" \
  --min-count "${EXECUTION_REMEDIATION_MIN_COUNT:-2}" \
  --min-ratio "${EXECUTION_REMEDIATION_MIN_RATIO:-0.2}" \
  --dedupe-hours "${EXECUTION_REMEDIATION_DEDUPE_HOURS:-24}"
