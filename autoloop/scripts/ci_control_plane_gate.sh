#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export CONTROL_PLANE_GATE_WINDOW_SIZE="${CONTROL_PLANE_GATE_WINDOW_SIZE:-15}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" && -x "./.venv/bin/python" ]]; then
  PYTHON_BIN="./.venv/bin/python"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" scripts/run_control_plane_matrix.py >/dev/null
"$PYTHON_BIN" scripts/run_control_plane_slo.py >/dev/null

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

root = Path(".")
slo_path = root / "runtime" / "metrics" / "control_plane_slo_report.json"
schema_path = root / "schemas" / "contracts" / "evidence_record.schema.json"

if not slo_path.exists():
    raise SystemExit("missing SLO report")
if not schema_path.exists():
    raise SystemExit("missing evidence schema")

slo = json.loads(slo_path.read_text(encoding="utf-8"))
schema = json.loads(schema_path.read_text(encoding="utf-8"))

metrics = slo.get("metrics", {})
thresholds = slo.get("release_gate_thresholds", {})

primary = float(metrics.get("primary_failure_hit_rate", 0.0))
event = float(metrics.get("event_completeness_rate", 0.0))
terminal = float(metrics.get("terminal_state_consistency_rate", 0.0))
unknown = float(metrics.get("unknown_failure_rate", 1.0))
required_detail_missing = float(metrics.get("required_test_failure_detail_missing_rate", 1.0))

if primary < float(thresholds.get("primary_failure_hit_rate_min", 0.95)):
    raise SystemExit(f"primary_failure_hit_rate gate failed: {primary}")
if event < float(thresholds.get("event_completeness_rate_min", 0.95)):
    raise SystemExit(f"event_completeness_rate gate failed: {event}")
if terminal < float(thresholds.get("terminal_state_consistency_rate_min", 0.95)):
    raise SystemExit(f"terminal_state_consistency_rate gate failed: {terminal}")
if unknown > float(thresholds.get("unknown_failure_rate_max", 0.05)):
    raise SystemExit(f"unknown_failure_rate gate failed: {unknown}")
if required_detail_missing > float(thresholds.get("required_test_failure_detail_missing_rate_max", 0.0)):
    raise SystemExit(
        f"required_test_failure_detail_missing_rate gate failed: {required_detail_missing}"
    )

required_fields = set(schema.get("required", []))
for field in ("terminal_state", "failure_events", "event_log_file"):
    if field not in required_fields:
        raise SystemExit(f"schema gate failed: required field missing -> {field}")
PY

echo "control plane gate passed"
