# Quentin Harden Loop: OpenClaw Atomic Porting Guide

This document defines the technical implementation path for "hardening" the Quentin (Project Taylor) cognitive architecture by porting high-value atomic components from OpenClaw. 

It complements `docs/runbooks/OPENCLAW_PORTING_TASKS.md` and `docs/runbooks/BRAIN_HARDENING_PLAN.md`.

## 1. Perception & Sensing Hardening (P1-P2)

### A. Head/Tail Content Truncation
- **Source:** OpenClaw `bootstrap.ts` (70% Head / 20% Tail / Marker).
- **Goal:** Prevent context blindness where the model only sees the start of a large file but misses the entry point or exports at the end.
- **Quentin Target:** `quentin/infra/text/truncation.py`.
- **Logic:** 
  - If file > `MAX_CHARS`:
    - Keep `MAX_CHARS * 0.7` from top.
    - Insert `[... TRUNCATED ...]` marker.
    - Keep `MAX_CHARS * 0.2` from bottom.

### B. Bootstrap Anchor Files (Context Snapshots)
- **Goal:** Ensure critical "system laws" (AGENTS.md, TODOs, PathGuard rules) are *always* in the L1 context, regardless of session history.
- **Quentin Target:** `quentin/cognitive/context_snapshots/bootstrap_files.py`.
- **Anchor List:**
  - `AGENTS.md` (Role definitions)
  - `TODO_TAYLOR_EVOLUTION.md` (Current mission)
  - `quentin/mutable/HEARTBEAT.md` (User intent overrides)
  - All `extensions/tools/**/manifest.yaml` (Tool registry documentation)

## 2. Executor & Tool-Call Hardening (P0-P3)

### A. Idempotency Gate (FS Hardening)
- **Goal:** Prevent "destructive rewrites" when the goal is already achieved.
- **Quentin Target:** `quentin/tools/filesystem.py` (`fs_write_file`).
- **Implementation:**
  - Before writing: check `exists`.
  - If exists: compare `sha256(new_content)` with `sha256(existing)`.
  - If match: return `{"status": "skipped", "reason": "unchanged"}`.

### B. Tool Result Guard (Causality Closure)
- **Goal:** Ensure every `tool_call` from the LLM has a corresponding `tool_result` in the session transcript.
- **Quentin Target:** `quentin/llm/tool_call_protocols/base.py` or `quentin/llm/client.py`.
- **Implementation:**
  - Track `pending_calls` in the current turn.
  - If the loop finishes without a result for a call (e.g., executor crash), synthesize a `synthetic_error` result.
  - Prevents "State Drift" where the LLM thinks a tool is running but the system has lost track.

## 3. Parsing & Health Hardening (P4)

### A. Sanitization & Fingerprinting
- **Goal:** Stop "Chatty LLMs" from polluting health metrics with format warnings.
- **Quentin Target:** `quentin/llm/sanitize.py`.
- **Logic:**
  - Strip Markdown code blocks (```json ... ```).
  - Strip trailing prose ("Here is the file you asked for...").
  - Map specific regex patterns (from OpenClaw `errors.ts`) to "Soft Events" (Metric-only) instead of "Hard Failures".

## Execution Sequence

1. **Atomic Tooling:** Implement `fs_write_file` idempotency first.
2. **Text Utils:** Implement Head/Tail truncation.
3. **Context Layer:** Add `BootstrapFilesProvider`.
4. **Safety Closure:** Implement `ToolResultGuard`.
5. **Metric Refinement:** Apply `sanitize_user_facing_text` and update `SelfAwareness`.

---
*Created on: 2026-02-14*
*Status: Approved for Atomic Porting*
