# Gemini Execution Plan and UAT (Project Taylor)

This document defines the execution contract, implementation standards, and UAT (User Acceptance Testing) gates for Gemini CLI agents working on Project Taylor.

## 1. Execution Principles

### 1.1 Robustness & Idempotency
- **Format Robustness**: All code changes must adhere to the project's formatting (dataclasses over raw dicts where applicable, type hints mandatory).
- **Semantic Idempotency**: Every script and task should be safe to run multiple times. Check for existence before creation; use UPSERT logic for configuration.
- **Fast-Path Optimization**: If a component is already at the target state (verified via evidence files or checksums), skip redundant execution.

### 1.2 Plan-Execution Contract
- **Explain Before Acting**: Never call a tool in silence. Summarize the step's goal.
- **Multi-step Persistence**: Maintain a structured plan even after sub-step failures. Avoid the "single-step fallback" trap.
- **Atomic Commits**: Group related logic changes into single PR-like completions (do not commit unless asked).

### 1.3 Observability
- All new features must inject telemetry into `quentin/traces/`.
- Critical safety decisions must be logged to `data/security_audit.jsonl` (P3/P5 compliant).

---

## 2. Target Implementation Modules

| Module | Purpose | Key Files |
| :--- | :--- | :--- |
| **Evolution** | Strategy-driven optimization | `quentin/evolution/proposal_*` |
| **Concurrency** | Multi-tenant isolation | `quentin/infra/concurrency/lane_policy.py` |
| **Safety** | Final hard-logic boundaries | `quentin/constitution/`, `quentin/safety/` |
| **Platform** | External SDKs and Specs | `quentin/platform/`, `specs/oqs/` |
| **Governance** | RBAC and Change Control | `quentin/governance/` |

---

## 3. Required Test Matrix

### 3.1 Unit Tests (Mandatory)
- [ ] **Schema Validation**: Verify all new dataclasses/models handle missing/null fields.
- [ ] **Logic Gates**: Verify that `ProposalGate` and `ConstraintVerifier` correctly block invalid inputs.
- [ ] **Crypto/Signing**: Verify signature verification round-trips.

### 3.2 Integration Tests (Mandatory)
- [ ] **API Loop**: End-to-end task execution via `/run-task` with session isolation.
- [ ] **Lifecycle**: Promote an experimental capability to trusted and verify API visibility.
- [ ] **DR Flow**: Backup, corrupt, restore, and verify consistency.
- [ ] **Federation**: Mock node registration and sync packet filtering.

---

## 4. UAT Gates (Quantifiable)

### Gate 1: Connectivity & Baseline
- [ ] `GET /health/p3` returns `200 OK` with all P3 flags present.
- [ ] All P0-P12 Feature Flags are mapped in `config/openclaw_parity.yaml`.

### Gate 2: Security & Compliance
- [ ] `data/security_audit.jsonl` contains at least one `tool_call` entry with a valid `decision`.
- [ ] `AuditChain` integrity check returns `True` for a non-empty log.

### Gate 3: Scalability & Isolation
- [ ] `test_multi_tenant_lane_isolation` passes with concurrent requests.
- [ ] Quota 429 errors are correctly returned and logged.

### Gate 4: Autonomy & Evolution
- [ ] At least one `Milestone` is generated and prioritized by the `RoadmapScheduler`.
- [ ] A/B benchmark report exists in `logs/bench/p4/`.

### Gate 5: Ecosystem & Standards
- [ ] `OQSValidator` passes for `specs/oqs/v1/tools.yaml`.
- [ ] `GET /capabilities` returns a non-empty list including registered platform tools.

---

## 5. One-Click Verification & Deliverables

### Command
```bash
# Full regression and UAT check
PYTHONPATH=. pytest tests/unit tests/integration tests/research
```

### Deliverables Checklist
1. **Core Logic**: Fully implemented modules in `quentin/`.
2. **Persistence**: Valid data in `data/` (audit, snapshots, tower logs).
3. **Evidence**: Updated `TODO_EVIDENCE_AUDIT.md` and acceptance checklists.
4. **Docs**: Updated Runbooks in `docs/runbooks/` and Guides in `docs/platform/`.
