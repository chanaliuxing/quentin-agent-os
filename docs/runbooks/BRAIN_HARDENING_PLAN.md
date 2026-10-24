# Quentin Brain Hardening Plan (Focused Sensing + Idempotent Execution + Format Robustness) - COMPLETE ✅

Context: this plan targets the recurring failures seen in recent `verify_system.py` runs (e.g. goal `a3a45f09...`), especially:
- Pre-sensing misses relevant files and returns `not_done` incorrectly.
- Executor overwrites files even after observing they already exist.
- `failover_reason=format` appears even when work succeeded (false alarms).
- Rewrites can *regress* file quality (e.g. manifest loses required fields).

**STATUS: ALL PHASES IMPLEMENTED AND VERIFIED (Feb 14, 2026)**

---

## Goals (What “fixed” means) - ✅ ACHIEVED

1. **先看再动**: For any mutating action (write/replace/mkdir), the system performs a cheap deterministic pre-check and skips if already satisfied. (Verified in `tests/unit/test_fs_write_file_idempotent.py`)
2. **幂等可重复**: Running the same task twice should produce *no destructive writes* on the second run. (Verified in `tests/unit/test_executor_autofingerprint.py`)
3. **格式不再误伤**: “format salvage” is tracked, but it does not poison failure-rate / immune loop unless it actually blocks execution. (Implemented in `SelfAwarenessEngine`)
4. **不允许逻辑退化**: Writes that would drop required fields or violate schema are blocked (fail-closed) and force repair. (Implemented in `fs_write_file` manifest validation)
5. **可观测可验收**: For every step, logs include: action, pre-check evidence, whether it was skipped, and why. (Implemented in `Executor` and `SensingReport`)

---

## Phase 0 (Foundation): Make destructive tools idempotent-by-default - ✅ COMPLETE

### P0.1 `fs.write_file` skip-if-unchanged (core) - ✅
**Where**: `quentin/tools/filesystem.py` (`fs_write_file`)
**Verified**: Done. Second write with same content returns `unchanged_skipped`.

### P0.2 Content-aware fingerprints when planner omitted/unstable - ✅
**Where**: `quentin/execution/executor.py`
**Verified**: Done. Executor auto-generates hash based on tool args if planner fingerprint is missing.

### P0.3 Fail-closed schema validation for known high-risk files - ✅
**Where**: `quentin/tools/filesystem.py`
**Verified**: Done. Writes to `manifest.yaml` fail if required metadata keys are missing.

---

## Phase 1 (Focused Sensing 2.0): Stop using global tree snapshots for “done” decisions - ✅ COMPLETE

### P1.1 Replace “tree slice” with targeted probes - ✅
**Where**: `quentin/cognitive/loop_impl.py`
**Verified**: Done. `SensingReport` (JSON) replaces text tree, includes file hashes.

### P1.2 Pre-sensing returns evidence-rich verdict - ✅
**Verified**: Done. Council returns `already_done` with confidence and `evidence_summary`.

---

## Phase 2 (Dynamic Execution): “observe → decide → act”, prune outdated plans - ✅ COMPLETE

### P2.1 Add a last-mile guard before any mutation - ✅
**Verified**: Done. Implemented inside tool layer for `write_file`, `mkdir`, and `search_replace`.

### P2.2 Executor records “skipped because satisfied” - ✅
**Verified**: Done. Trace events record `idempotent_hit` and reasons.

---

## Phase 3 (Format Robustness): Stop “format” from corrupting health signals - ✅ COMPLETE

### P3.1 Split “format salvage” from “execution failure” - ✅
**Where**: `quentin/cognitive/self_awareness.py`
**Verified**: Done. `SelfAwarenessEngine` ignores `format` failover if execution succeeded.

### P3.2 Standardize JSON extraction and repair - ✅
**Verified**: Done. Unified parsing logic in `ollama_client` and `council/manager`.

---

## Phase 4 (Governance + Performance): Local laptop should not self-sabotage - ✅ COMPLETE

### P4.1 Local fast path for low-risk councils - ✅
**Where**: `quentin/council/manager.py`
**Verified**: Done. `QUENTIN_COUNCIL_LOCAL_FAST_PATH=1` uses single member for pre-sensing/planner/done.

### P4.2 ImmuneLoop latency thresholds differentiated by local/remote - ✅
**Verified**: Done. Latency policies now allow for slower local inference without triggering emergency degradation.

---

## Phase 5 (Permissions + Policy Transparency) - ✅ COMPLETE

### P5.1 Make write roots visible to the planner/executor - ✅
**Where**: `quentin/cognitive/perception/policy_provider.py`
**Verified**: Done. `system_policies` injected into `SensingReport` visible to the brain.

---

## Acceptance Criteria (Release Gate) - ✅ MET

### A. Correctness & Idempotency
- Running task twice results in **0** destructive writes on second run. ✅
- Manifest validation prevents broken plugin registration. ✅

### B. Observability
- Mutating steps log precheck evidence and skip decisions. ✅

### C. Health Signals
- Successful runs with salvage show `failure_rate == 0.0`. ✅

### D. Performance
- Council uses fast path for simple operations. ✅

---

## Verification Commands Used

- `pytest -q tests/unit/test_fs_write_file_idempotent.py tests/unit/test_executor_autofingerprint.py tests/unit/test_pre_sensing_report_focus.py`
- `pytest -q tests/unit/test_graph_query_by_intent.py tests/integration/test_skill_mining_circular_dependency.py`
- Manual `verify_system.py` runs.
