# Plan: Autonomy + Self-Evolution (Gemini Execution Guide)

Date: 2026-02-08  
Repo: `quentin-agent-os`  
Working branch (current): `ai-dev/auto-fix-557654` @ `8aa56de`

Audience:
- This document is written for **Gemini (or any external agent)** to take over large chunks of implementation safely.
- It assumes no prior context besides this repo.

Primary goal:
- Reach “the brain runs itself” and **continuously improves** under governance:
  1. Pull tasks automatically.
  2. Run Cognitive/Sleep/Immune loops.
  3. Detect gaps/anomalies.
  4. Generate patch proposals.
  5. Evaluate patches (tests/bench).
  6. Apply in sandbox only; record release protocol; never bypass SafetyKernel.
  7. Measure outcomes and decide promotion.

Non-goals (must keep):
- Do not rewrite `blueprint.md` narrative.
- Do not enable real network providers by default.
- Do not allow auto-apply outside sandbox.
- Do not weaken `meta_agent/safety/*` path policy or `quentin/kernel/*` SafetyKernel governance.

---

## 0. Current State Snapshot (What Is Already Implemented)

### 0.1 Canonical runtime entrypoints
- CLI: `python -m quentin.cli.qctl ...`
  - `run-task`: main CognitiveLoop path (offline by default when `LLM_STUB=1`)
  - `brain-run`: one brain cycle (Cognitive + Sleep + Immune + optional PatchFlow)
  - `task-enqueue`, `task-run-queue`: file-backed queue
  - `blueprint-autopatch`: blueprint gaps → self-prog proposals (no auto-apply from this entrypoint)
- Daemon: `scripts/run_brain_daemon.py`

### 0.2 Offline-first autonomy primitives (L0/L1)
- Brain daemon loop: `quentin/runtime/brain_daemon.py`
- File-backed TaskQueue (JSONL): `quentin/runtime/task_queue.py`
- Task Sources v1:
  - blueprint gaps → tasks
  - PatchFlow backlog → tasks
  - Code: `quentin/runtime/task_sources.py`
  - CLI: `python -m quentin.cli.qctl task-source-run --max-blueprint-tasks 25`
- PatchFlow pipeline (governed, sandbox-only auto-apply):
  - Code: `meta_agent/patchflow/orchestrator.py`
  - Queue: `meta_agent/patchflow/queue.py` (env `META_AGENT_PATCH_QUEUE_PATH`)
  - Safety checker: `meta_agent/safety/checker.py` + `meta_agent/safety/policy.py`

### 0.3 Patch proposal flow closure (bridge)
- SelfProgrammingEngineV2 writes patch proposals to PatchStore (`data/patches.json`).
- PatchFlow consumes PatchQueue (`data/patches/patch_queue.jsonl`).
- Bridge (NEW): PatchStore → PatchQueue
  - Code: `meta_agent/patchflow/store_bridge.py`
  - Enabled via: `META_AGENT_PATCHFLOW_SYNC_STORE=1`
  - Integrated in `PatchFlowOrchestrator.run_cycle()`.

### 0.4 Blueprint gap scanning / autopatch
- Blueprint scanner: `quentin/blueprint/tracker.py` reads `blueprint/spec_v3.json`
- Autopatcher: `quentin/blueprint/auto_patcher.py`
- CLI wrapper: `python -m quentin.cli.qctl blueprint-autopatch --run-selfprog --json`
- Brain daemon maintenance mode (NEW):
  - `QUENTIN_BRAIN_RUN_BLUEPRINT_AUTOPATCH=1` (sandbox only)
  - Runs autopatch when idle, proposes patches (does not auto-apply).

### 0.5 Benchmarks and tests already exist
- Memory recall bench: `scripts/bench_memory_recall.py` + `tests/integration/test_bench_memory_recall_runs.py`
- TaskQueue throughput bench: `scripts/bench_task_queue_offline.py`
- Autonomy E2E bench (offline): `scripts/bench_autonomy_end_to_end.py`
- PatchFlow bridge tests:
  - `tests/unit/test_patchflow_store_bridge.py`
  - `tests/unit/test_patchflow_sync_store_hook.py`
- Baseline: `pytest -q` passes on this branch (currently ~237 tests).

### 0.6 Real LLM calls are supported but opt-in
- Canonical LLM entrypoint: `quentin/llm/client.py:call_llm`
- Offline stub: `LLM_STUB=1` forces deterministic JSON outputs.
- Provider selection: `LLM_PROVIDER=openai|gemini|deepseek|openrouter|ollama`
- SafetyKernel guard and audit are integrated for remote calls.

---

## 1. Definition of “Brain Auto-Evolves” (Final Acceptance Criteria)

We consider the system to reach “automatic self-evolution” when all are true:

### 1.1 Always-on execution
- Brain can run in daemon mode, continuously, without manual task injection.
- It creates work for itself (task sources) and drains the queue.

### 1.2 Non-bypassable governance
- All high-impact actions (LLM/tool/patch/experiment/deploy/storage writes) go through SafetyKernel and are logged.
- Auto-apply only occurs in sandbox and is rollback-safe.

### 1.3 Closed feedback loop (L3→L2→L1)
- A measurable improvement loop exists:
  1. Detect a gap or anomaly.
  2. Create a remediation task.
  3. Propose a patch (self-prog).
  4. Evaluate with tests + benchmark.
  5. Decide (approve/reject) with governance.
  6. Apply in sandbox and re-run validations.
  7. Record metrics deltas; store report; update policy/routing/variants.

### 1.4 Measurable and reproducible
- Offline mode has deterministic benches and integration tests that validate the loop wiring.
- Real-provider mode is env-gated and budget-capped (canary).

---

## 2. Implementation Roadmap (Phases, DoD, Tests)

Each phase has:
- Deliverables
- How to test
- DoD (Definition of Done)
- Gate to proceed

### Phase A (P0): Make “Self-Directed” robust (Task Sources v2)

Problem:
- Task sources exist but are simplistic. We need **observability/anomaly** driven tasks.

Deliverables:
1. Add an anomaly detector producing remediation tasks:
   - Source: `quentin/observability/service.py` (or a new `quentin/observability/anomaly_detector.py`)
   - Signals (v1 thresholds):
     - consecutive LLM failures by provider/model/profile
     - memory recall latency spike
     - patchflow blocked rate spike
     - budget violations / denial spikes
2. Enqueue anomaly tasks via `quentin/runtime/task_sources.py`:
   - `QUENTIN_TASK_SOURCE_OBS=1`
   - Each queued task includes evidence payload in metadata.

Tests:
- Add unit tests for anomaly detection decisions (pure, deterministic).
- Add integration test:
  - Create a synthetic “overview snapshot” with spikes.
  - Run `qctl task-source-run`.
  - Assert tasks are enqueued with expected `metadata.kind`.

DoD:
- `python -m quentin.cli.qctl task-source-run` enqueues tasks from:
  - blueprint gaps (existing)
  - patchflow backlog (existing)
  - observability anomalies (new)
- `pytest -q` passes.

Gate to proceed:
- At least 1 anomaly path creates tasks deterministically offline.

---

### Phase B (P0): Make “Patch Proposal Generation” reliable and safe by default

Problem:
- We can autopatch from blueprint gaps, but self-prog must be more predictable, especially offline.

Deliverables:
1. Make `SelfProgrammingEngineV2` “offline deterministic” mode truly safe:
   - Use `CODER_BACKEND=deterministic` in offline runs to generate patches only in allowed roots.
   - Ensure proposed target file is always under allowed roots:
     - `quentin/mutable/**` or `meta_agent/tools/**`
2. Add a “proposal-only” mode for the engine:
   - The engine already supports `allow_auto_apply=False`.
   - Ensure it never tries to merge/commit branches unless explicitly enabled.

Tests:
- Unit test: deterministic run yields patch targets under `quentin/mutable/`.
- Integration test: run `blueprint-autopatch --run-selfprog` with deterministic backend and ensure PatchStore contains entries.

DoD:
- Offline:
  - `LLM_STUB=1 CODER_BACKEND=deterministic python -m quentin.cli.qctl blueprint-autopatch --run-selfprog --json`
  - Produces at least 1 patch in `data/patches.json` with safe target files.

Gate to proceed:
- The patch proposal pipeline can be exercised without a real LLM/CLI.

---

### Phase C (P0): Close “Proposal → Evaluation → Apply → Rollback” loop under PatchFlow

Problem:
- PatchFlow runs, but we need a consistent default behavior for evaluations and deterministic benches.

Deliverables:
1. Extend PatchFlow evaluation to always include:
   - safety check (already)
   - diff stats (already)
   - optional tests (already)
   - optional benchmark suite (NEW): run one or more bench scripts in sandbox
     - Env:
       - `META_AGENT_PATCHFLOW_RUN_BENCH=1`
       - `META_AGENT_PATCHFLOW_BENCH_CMD="python scripts/bench_memory_recall.py ..."`
2. Persist a structured report per patchflow item (schema-stable):
   - Path: `data/patchflow_reports/{patchflow_id}.json`
   - Include:
     - safety decision
     - tests outcome
     - bench outcome (latency/cost deltas)
     - rollback status if any

Tests:
- Unit test: when bench flag is on, PatchFlow calls bench cmd (use a tiny echo script / stub command).
- Integration test: run PatchFlow in sandbox with a known patch proposal and ensure report file exists.

DoD:
- `META_AGENT_PATCHFLOW_SYNC_STORE=1 META_AGENT_PATCHFLOW_RUN_TESTS=1 META_AGENT_PATCHFLOW_AUTO_APPLY=0 python -c "...PatchFlowOrchestrator().run_cycle()"`
  - Processes queue items deterministically without applying.
- Optional apply path remains sandbox-only and rollback-safe.

Gate to proceed:
- PatchFlow has a stable report artifact and can run tests/bench in the loop.

---

### Phase D (P1): Promote script-level “evolution loop” into daemon maintenance (L3→L2→L1)

Problem:
- We have pieces (experiments, patchflow, task sources), but not one canonical always-on cycle.

Deliverables:
1. Add a “maintenance cycle” stage inside BrainDaemon:
   - Sequence while idle:
     1. run task sources
     2. run blueprint autopatch (proposal)
     3. run patchflow cycle (evaluate/queue status)
     4. (optional) run experiments/evals for variants
2. Add explicit flags and conservative defaults:
   - `QUENTIN_TASK_SOURCES_ENABLE=1`
   - `QUENTIN_BRAIN_RUN_BLUEPRINT_AUTOPATCH=1` (sandbox only)
   - `META_AGENT_PATCHFLOW_RUN=1`
   - `META_AGENT_PATCHFLOW_SYNC_STORE=1`
   - `META_AGENT_PATCHFLOW_AUTO_APPLY=0` by default

Tests:
- Integration test (offline):
  - Set env for stub LLM and deterministic coder backend.
  - Enqueue 0 tasks; run daemon queue worker for a few seconds; assert it created proposals and processed patchflow queue.

DoD:
- A single command can run the maintenance pipeline offline:
  - `LLM_STUB=1 CODER_BACKEND=deterministic QUENTIN_TASK_SOURCES_ENABLE=1 QUENTIN_BRAIN_RUN_BLUEPRINT_AUTOPATCH=1 META_AGENT_PATCHFLOW_RUN=1 META_AGENT_PATCHFLOW_SYNC_STORE=1 python scripts/run_brain_daemon.py --from-queue --max-tasks 1`
  - Must terminate cleanly and produce:
    - trace event(s)
    - patchflow queue updates or reports

Gate to proceed:
- Offline always-on maintenance cycle is runnable and produces artifacts.

---

### Phase E (P2): Real-provider “canary brain run” (budgeted, auditable)

Problem:
- Real LLM calls must be safe: budget caps, rate limits, failover, and auditable trails.

Deliverables:
1. Canary mode:
   - `QUENTIN_CANARY=1` (new or use existing budget flags)
   - strict max calls/minute
   - strict max tokens/day
   - forbid autopatch auto-apply
2. Add a canary smoke runner:
   - Script: `scripts/run_canary_brain_once.py` (new)
   - DoD: captures audit + trace, and never applies patches.

Tests:
- Env-gated integration test:
  - Only runs when keys are provided: `REAL_LLM_SMOKE=1`
  - Ensures audit/trace has `remote_meta.usage`.

DoD:
- Canary run produces:
  - policy decision logs
  - audit logs
  - trace logs
  - observed tokens/cost stats

Gate to proceed:
- One controlled real-provider run is reproducible and safe.

---

## 3. Rules for Gemini (How to Work Without Breaking the System)

### 3.1 Mandatory safety rules
- Never weaken `meta_agent/safety/policy.py` forbidden roots.
- Never enable auto-apply by default; sandbox-only enforcement must stay.
- Any new feature must be env-gated and default-off if it can cause real-world cost or filesystem changes.

### 3.2 Testing rules
- Every new autonomy feature must ship with:
  - at least 1 unit test (pure logic)
  - at least 1 integration test (script runs, exit code 0)
- Always run: `pytest -q` before committing.

### 3.3 Artifacts and git hygiene
- Do not commit `data/`, `logs/`, `chroma_db_code_chunks/` runtime artifacts.
- Prefer writing reports under `data/` (already gitignored).

---

## 4. “When to Advance Phase” Checklist (Single-line Gates)

- A→B: Observability anomalies generate tasks offline deterministically.
- B→C: Blueprint autopatch generates safe patch proposals offline (targets under allowed roots).
- C→D: PatchFlow creates structured reports and can run tests/bench optionally.
- D→E: Daemon maintenance loop runs end-to-end offline without manual injection.
- E done: Canary run works with strict budget and full audit/trace.

---

## 5. Quick Commands (Copy/Paste)

Offline smoke:
```bash
LLM_STUB=1 python -m quentin.cli.qctl run-task --input-text "hello"
```

Run task sources:
```bash
python -m quentin.cli.qctl task-source-run --max-blueprint-tasks 10
```

Blueprint autopatch (proposal only; no auto-apply):
```bash
LLM_STUB=1 CODER_BACKEND=deterministic python -m quentin.cli.qctl blueprint-autopatch --run-selfprog --json
```

PatchFlow cycle (sync PatchStore → PatchQueue first):
```bash
META_AGENT_PATCHFLOW_SYNC_STORE=1 python -c "from meta_agent.patchflow.orchestrator import PatchFlowOrchestrator; print(PatchFlowOrchestrator().run_cycle())"
```

Daemon queue worker with maintenance:
```bash
LLM_STUB=1 CODER_BACKEND=deterministic \
QUENTIN_TASK_SOURCES_ENABLE=1 \
QUENTIN_BRAIN_RUN_BLUEPRINT_AUTOPATCH=1 \
META_AGENT_PATCHFLOW_RUN=1 META_AGENT_PATCHFLOW_SYNC_STORE=1 \
python scripts/run_brain_daemon.py --from-queue --max-tasks 1
```

Run all tests:
```bash
pytest -q
```

