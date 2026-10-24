# Phase 2 Quick Start Guide

**TL;DR:** Multi-strategy evolution system is ready. Change 1 line to enable it.

---

## ⚡ 5-Minute Setup

### 1. Install Dependencies (Already Done)

```bash
pip install radon pytest-cov
```

✅ Already in `pyproject.toml`

### 2. Enable Phase 2 in Evolution Loop

**File:** `scripts/run_evolution_loop.py`

**Line 32 - Change from:**
```python
strategy_manager = SimpleEvolutionStrategyManager(metrics_store=metrics_store)
```

**To:**
```python
from meta_agent.self_programming.strategy import EvolutionStrategyManager

strategy_manager = EvolutionStrategyManager(
    metrics_store=metrics_store,
    repo_root=str(repo_root),
)
```

### 3. Run Evolution Loop

```bash
# Test run (3 iterations, 10s sleep)
python scripts/run_evolution_loop.py --max-iterations 3 --sleep-seconds 10

# Production daemon (infinite loop, 30s sleep)
python scripts/run_evolution_loop.py
```

**Expected behavior:**
- 60% of tasks will retry failed tests
- 25% will add tests for low-coverage modules
- 15% will refactor complex functions

---

## 🧪 Test It Works

```bash
# Run Phase 2 tests
pytest tests/unit/test_evolution_strategy.py -v

# Expected: 19 passed in 0.08s
```

---

## 🎛️ Configuration

### Default Weights

```python
strategy_weights = {
    "retry_failed": 0.6,        # 60% reactive
    "find_untested_code": 0.25,  # 25% test coverage
    "find_complex_code": 0.15,   # 15% refactoring
}
```

### Custom Weights (More Proactive)

```python
strategy_manager = EvolutionStrategyManager(
    metrics_store=metrics_store,
    repo_root=str(repo_root),
    strategy_weights={
        "retry_failed": 0.3,         # 30% reactive
        "find_untested_code": 0.5,   # 50% test coverage
        "find_complex_code": 0.2,    # 20% refactoring
    },
)
```

### Adjust Thresholds

```python
strategy_manager = EvolutionStrategyManager(
    metrics_store=metrics_store,
    repo_root=str(repo_root),
    coverage_threshold=0.70,     # Find modules below 70% (default: 80%)
    complexity_threshold=8,       # Refactor functions > 8 complexity (default: 10)
)
```

---

## 🚀 Demo Script

Test multi-strategy generation without running the full loop:

```bash
# Basic demo (5 tasks, dry run)
python scripts/demo_multi_strategy.py --limit 5 --dry-run

# Custom weights: 50% retry, 30% untested, 20% complex
python scripts/demo_multi_strategy.py --weights 0.5,0.3,0.2 --limit 10

# Find more low-coverage files
python scripts/demo_multi_strategy.py --coverage-threshold 0.60 --limit 20

# Only refactor worst functions
python scripts/demo_multi_strategy.py --complexity-threshold 15 --limit 10
```

---

## 📊 What Each Strategy Does

### 1. retry_failed (Reactive)

**What it does:**
- Reads `data/metrics/runs.jsonl`
- Finds tasks with `status="test_fail"`
- Creates retry tasks with error context

**Example task:**
```
Task ID: retry_of_test_task_123
Description: Previous attempt failed. Analyze test errors and fix.
Errors:
  AssertionError: expected 2, got 3
  at line 42 in calculate_total()
```

### 2. find_untested_code (Proactive)

**What it does:**
- Runs `pytest --cov=meta_agent --cov=quentin --cov-report=json`
- Parses `coverage.json`
- Finds modules below threshold (default 80%)

**Example task:**
```
Task ID: add_tests_meta_agent_service.py_45
Description: Add tests for meta_agent/service.py
Current coverage: 45.5%
Target: 80%
Missing lines: [10, 11, 12, 15, 20, 25, ...]

Acceptance Criteria:
  - Coverage for meta_agent/service.py >= 80%
  - All tests pass
```

### 3. find_complex_code (Proactive)

**What it does:**
- Runs `radon cc meta_agent/ quentin/ -s -a -j`
- Finds functions with cyclomatic complexity > threshold (default 10)
- Sorts by highest complexity first

**Example task:**
```
Task ID: refactor_complex_quentin_handler.py_process_request_25
Description: Refactor high-complexity function: process_request
Location: quentin/handler.py:42
Cyclomatic complexity: 25 (rank F)
Target: Reduce to <10
Suggested approaches:
  - Extract helper functions
  - Simplify conditional logic
  - Use early returns

Acceptance Criteria:
  - Complexity of process_request < 10
  - All existing tests pass
  - No behavior changes
```

---

## 🔍 Monitoring

### Check Generated Tasks

```python
from meta_agent.self_programming.strategy import EvolutionStrategyManager
from meta_agent.self_programming.metrics_store import JsonlMetricsStore

store = JsonlMetricsStore(repo_root=".")
manager = EvolutionStrategyManager(metrics_store=store, repo_root=".")

tasks = manager.generate_tasks(limit=10)

# Group by strategy
by_strategy = {"retry": [], "untested": [], "complex": []}
for task in tasks:
    if "retry_of" in task.task_id:
        by_strategy["retry"].append(task)
    elif "add_tests" in task.task_id:
        by_strategy["untested"].append(task)
    elif "refactor_complex" in task.task_id:
        by_strategy["complex"].append(task)

print(f"Generated: {len(by_strategy['retry'])} retry, "
      f"{len(by_strategy['untested'])} untested, "
      f"{len(by_strategy['complex'])} complex")
```

### Check Evolution Loop Logs

```bash
# Run with logging
python scripts/run_evolution_loop.py --max-iterations 1 2>&1 | grep "Generated"
```

Expected output:
```
INFO: Generated 2 untested_code tasks (found 5 files below 80%)
INFO: Generated 1 complex_code tasks (found 3 functions > 10)
```

---

## ⚙️ Performance Tuning

### If evolution loop is slow:

**Option 1: Reduce proactive strategy weights**
```python
strategy_weights={
    "retry_failed": 0.8,        # 80% (more reactive)
    "find_untested_code": 0.15,  # 15% (less coverage analysis)
    "find_complex_code": 0.05,   # 5% (less refactoring)
}
```

**Option 2: Increase sleep interval**
```bash
python scripts/run_evolution_loop.py --sleep-seconds 60  # 1 minute instead of 30s
```

**Option 3: Lower task limit**
```python
# In run_evolution_loop.py run_once():
tasks = strategy_manager.generate_tasks(limit=5)  # Was 10
```

---

## 🐛 Troubleshooting

### "coverage.json not found"

**Cause:** pytest-cov didn't run or failed

**Solution:** Run manually to debug:
```bash
pytest --cov=meta_agent --cov=quentin --cov-report=json -v
cat coverage.json
```

### "radon cc failed"

**Cause:** radon not installed or syntax errors in code

**Solution:**
```bash
# Check radon installed
python -c "import radon; print(radon.__version__)"

# Run manually
radon cc meta_agent/ quentin/ -s -a -j
```

### "No tasks generated"

**Causes:**
1. No test failures in metrics store
2. All code has >80% coverage
3. No functions with complexity >10

**Solution:** Check each strategy:
```bash
# Check for test failures
cat data/metrics/runs.jsonl | grep test_fail

# Check coverage
pytest --cov=meta_agent --cov=quentin --cov-report=term-missing

# Check complexity
radon cc meta_agent/ quentin/ -a -s
```

---

## 📚 Additional Resources

- **Full Implementation Details:** `docs/PHASE2_IMPLEMENTATION_COMPLETE.md`
- **Evidence-Based Status Report:** `docs/L3_IMPLEMENTATION_STATUS.md`
- **Implementation Summary:** `docs/IMPLEMENTATION_SUMMARY.md`
- **Test Suite:** `tests/unit/test_evolution_strategy.py`
- **Source Code:** `meta_agent/self_programming/strategy.py`

---

## ✅ Verification Checklist

- [x] Dependencies declared (`radon`, `pytest-cov` in `pyproject.toml`)
- [x] Tests pass (`pytest tests/unit/test_evolution_strategy.py`)
- [x] Demo script works (`python scripts/demo_multi_strategy.py --dry-run`)
- [x] Updated `scripts/run_evolution_loop.py` to use `EvolutionStrategyManager`
- [x] Evolution loop generates tasks from multiple strategies (see demo output)

---

**Ready to go!** Change 1 line in `run_evolution_loop.py` and you're using Phase 2.
