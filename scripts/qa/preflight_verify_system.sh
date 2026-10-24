#!/bin/bash
set -e

echo "=== Gemini Preflight Check ==="

# 1. Check directories
for dir in "quentin/execution" "quentin/planning" "quentin/council" "data/execution/idempotency"; do
    if [ -d "$dir" ]; then
        echo "[OK] Directory $dir exists."
    else
        echo "[WARN] Directory $dir missing."
        mkdir -p "$dir"
    fi
done

# 2. Check ruff
if command -v ruff &> /dev/null; then
    echo "[OK] ruff is installed."
else
    echo "[FAIL] ruff is missing. Please install it for quality gate."
    exit 1
fi

# 3. Check verify_system.py
if [ -f "verify_system.py" ]; then
    echo "[OK] verify_system.py found."
else
    echo "[FAIL] verify_system.py missing."
    exit 1
fi

# 4. Optional Champion runtime guard for rollout/canary pipelines
if [ "${QUENTIN_REQUIRE_CHAMPION:-0}" = "1" ]; then
    echo -n "[Champion Guard] Verifying champion runtime... "
    if python scripts/check_champion_runtime.py --strict > /tmp/check_champion_runtime.out 2>&1; then
        echo "PASS"
    else
        echo "FAIL"
        cat /tmp/check_champion_runtime.out
        exit 1
    fi
fi

echo "=== Preflight Complete ==="
