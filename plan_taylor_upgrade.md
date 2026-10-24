# Plan: Taylor Upgrade (Lanes & Hybrid Search)

This plan outlines the steps to upgrade Project Taylor (Quentin) with **Lanes Concurrency Enforcement** and **Optimized Hybrid Search**, bringing its engineering robustness in line with OpenClaw.

## Phase 1: Enforce Concurrency Lanes (`quentin/cognitive`)

**Objective:** Prevent race conditions during agent execution and ensure thread-safe operations for self-programming.

1.  **Refactor `CognitiveLoop` (`quentin/cognitive/loop.py`)**:
    *   Import `get_lane_manager` from `quentin.infra.concurrency.lanes`.
    *   Wrap the `step()` and `run()` methods to acquire a **Session Lane Lock** before execution.
    *   Ensure the lock is released even if the loop crashes (try/finally).

2.  **Integrate Global Lane Throttle**:
    *   Use `get_lane_manager()._get_semaphore("main")` to limit total concurrent cognitive cycles (default: 1 or 2).
    *   This prevents API rate limits when multiple agents are running (e.g., Main + Critic + Researcher).

3.  **Update `MemoryFabric` (`quentin/memory/fabric.py`)**:
    *   Ensure memory writes (`remember`, `update`) respect the session lock or use a dedicated `db_write_lock` if independent of the session.

## Phase 2: Optimize Hybrid Search (`quentin/memory`)

**Objective:** Improve retrieval speed and accuracy by leveraging `sqlite-vec` and proper BM25 tuning.

1.  **Verify `sqlite-vec` Loading (`quentin/memory/store_sqlite_vec.py`)**:
    *   Add a diagnostic check on initialization to confirm the extension is loaded.
    *   If loading fails, log a clear warning and fallback to the (slower) Python implementation, but *notify the user*.

2.  **Tune Hybrid Scoring (`quentin/memory/store_sqlite.py`)**:
    *   Implement **Reciprocal Rank Fusion (RRF)** in `_finalize_recall` if not fully robust.
    *   Normalize BM25 scores: `score = 1 / (1 + max(0, raw_score))` (since FTS5 BM25 is lower-is-better).
    *   Ensure Vector Cosine Similarity is normalized to `0.0 - 1.0`.

3.  **Implement Real-Time Context Compaction (`quentin/cognitive/loop_impl.py`)**:
    *   Add a `check_context_window()` method to the loop.
    *   Before calling the LLM, check `used_tokens / max_context_tokens`.
    *   If usage > 80%, trigger `MemoryFabric.run_safe_forgetting()` or a dedicated `compact_session()` method *synchronously*.

## Phase 3: Verification

1.  **Concurrency Test**:
    *   Create `tests/concurrency/test_lanes_enforcement.py`.
    *   Spawn 5 parallel agents for the *same* session ID.
    *   Verify they run sequentially (total time ~= 5 * single run time).

2.  **Search Benchmark**:
    *   Create `tests/memory/benchmark_search.py`.
    *   Insert 1,000 dummy records.
    *   Compare `search(text="...")` vs `search(vector=[...])` latency.
    *   Verify `hybrid` search returns relevant results from *both* text and vector matches.

---

**Next Steps:**
1.  Approve this plan.
2.  I will execute Phase 1 (Lanes) immediately.
3.  I will then execute Phase 2 (Search).
