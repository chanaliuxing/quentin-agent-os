# Quentin Heartbeat & Inspection Guide

This file defines the periodic inspection routines for the Quentin Brain.
The system reads this file during the SleepLoop or periodic TaskSource runs.

## 1. High-Priority Checks
- [ ] Verify that all core services are responsive (LLM, Memory, KV).
- [ ] Check for pending patchflow proposals that require review.
- [ ] Inspect the last 10 error traces for recurring anti-patterns.

## 2. Maintenance SOPs
- If `vector_store_fallback` is detected, attempt to re-initialize ChromaDB.
- If `repeated_tool_call_loop` is found, inject a self-awareness note to the next session.

## 3. Custom Inspection Rules
- (User: add your specific project health checks here)
