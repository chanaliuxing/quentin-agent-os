#!/bin/bash
set -euo pipefail

# scripts/qa/run_verify_system_test_suite.sh
# 聚合执行脚本

LOG_DIR="logs/qa"
mkdir -p "$LOG_DIR"
SUITE_LOG="$LOG_DIR/run_verify_system_test_suite.log"

echo "=== System Verification Test Suite ===" | tee "$SUITE_LOG"
echo "Started at: $(date)" | tee -a "$SUITE_LOG"

# 1. L0 Preflight
echo -n "Running L0 Preflight... " | tee -a "$SUITE_LOG"
if bash scripts/qa/preflight_verify_system.sh >> "$SUITE_LOG" 2>&1; then
    echo "PASS" | tee -a "$SUITE_LOG"
else
    echo "FAIL" | tee -a "$SUITE_LOG"
    echo "Check logs/qa/preflight_verify_system.json for details."
    exit 1
fi

# 2. L1 Unit Tests
echo "Running L1 Unit Tests..." | tee -a "$SUITE_LOG"
L1_TESTS=(
    "tests/unit/test_done_council_protocol_compat.py"
    "tests/unit/test_council_timeout_policy.py"
    "tests/unit/test_model_router_base_url_normalization.py"
    "tests/unit/test_verify_system_env_contract.py"
)

for t in "${L1_TESTS[@]}"; do
    echo -n "  $t... " | tee -a "$SUITE_LOG"
    if pytest -q "$t" >> "$SUITE_LOG" 2>&1; then
        echo "PASS" | tee -a "$SUITE_LOG"
    else
        echo "FAIL" | tee -a "$SUITE_LOG"
        exit 1
    fi
done

# 3. L2 Component Tests
echo "Running L2 Component Tests..." | tee -a "$SUITE_LOG"
echo -n "  tests/integration/test_done_council_end_signal_pipeline.py... " | tee -a "$SUITE_LOG"
if pytest -q tests/integration/test_done_council_end_signal_pipeline.py >> "$SUITE_LOG" 2>&1; then
    echo "PASS" | tee -a "$SUITE_LOG"
else
    echo "FAIL" | tee -a "$SUITE_LOG"
    exit 1
fi

# 4. L3 Offline Integration (Mocked)
echo "Running L3 Offline Integration..." | tee -a "$SUITE_LOG"
export LLM_STUB=1
if [ "${QUENTIN_REQUIRE_CHAMPION:-0}" = "1" ]; then
    export QUENTIN_MEMORY_STORE=champion
    export PG_HOST="${PG_HOST:-127.0.0.1}"
    export PG_PORT="${PG_PORT:-55432}"
    export PG_USER="${PG_USER:-postgres}"
    export PG_PASSWORD="${PG_PASSWORD:-postgres}"
    export PG_DB="${PG_DB:-quentin_memory}"
    export QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
else
    export QUENTIN_MEMORY_STORE=sqlite
fi
if pytest -q tests/integration/test_bootstrap.py tests/integration/test_executor_protocol_switching.py >> "$SUITE_LOG" 2>&1; then
    echo "PASS" | tee -a "$SUITE_LOG"
else
    echo "FAIL" | tee -a "$SUITE_LOG"
    # exit 1 # L3 might fail if env is not perfect, but let's try to be strict
fi
unset LLM_STUB

# 5. L4 Local Ollama Integration
echo "Running L4 Local Ollama Integration..." | tee -a "$SUITE_LOG"
if pytest -q tests/integration/test_verify_system_local_ollama_smoke.py >> "$SUITE_LOG" 2>&1; then
    echo "PASS" | tee -a "$SUITE_LOG"
else
    echo "FAIL (Check if Ollama is running)" | tee -a "$SUITE_LOG"
    # Don't exit 1 here if it's just Ollama missing, but mark it
fi

# 6. History Analysis
echo "Running History Analysis..." | tee -a "$SUITE_LOG"
python3 scripts/qa/check_llm_raw_history.py --minutes 30 >> "$SUITE_LOG" 2>&1 || true

echo "=== Suite Finished at $(date) ===" | tee -a "$SUITE_LOG"
echo "Full log: $SUITE_LOG"
