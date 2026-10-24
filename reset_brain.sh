#!/bin/bash
echo "🧹 Starting Deep System Purge..."

# 1. Clear Cognitive Traces
rm -rf data/traces/*
rm -f data/traces.jsonl

# 2. Clear Task Queue and Goals
rm -f data/tasks/queue.jsonl
rm -f data/goals.jsonl

# 3. Clear Immune System History (Anomalies)
rm -rf data/immune_cases/*
rm -f data/immune_cases.jsonl

# 4. Clear Session State & Locks
rm -rf data/sessions/*
rm -rf data/runtime/session_locks/*
rm -f data/runtime/brain_guardrail_state.json

# 5. Clear Low-level Logs
rm -f logs/*.log
rm -f data/audit_events.jsonl
rm -f data/policy_decisions.jsonl

# 6. Re-create essential directories to avoid startup errors
mkdir -p data/traces data/sessions data/tasks data/immune_cases data/runtime/session_locks logs

echo "✨ System is now 100% CLEAN. Brain is in pristine state."
