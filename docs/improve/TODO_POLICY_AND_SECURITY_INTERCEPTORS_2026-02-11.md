# TODO: Policy + Security Interceptors Registry (Hard Logic)

Date: 2026-02-11
Scope: `quentin/kernel/*`, `quentin/security/*`, `tests/*`

Problem:
- SafetyKernel exists, but adding a new hard interceptor tends to be a direct edit in core code.
- OpenClaw-style "hard logic inner ring" should be composable and testable as a chain.

Goal:
- Introduce a registry/chain for:
  - path traversal checks
  - non-interactive enforcement (already partially exists)
  - command auditing / destructive detection
  - capability gating by environment/role/subagent
- Add an optional Human-in-the-Loop approval gate for risky-but-not-blocked actions (default OFF).
- Ensure interceptors are deterministic and emit consistent audit metadata.

Non-goals:
- Do not relax any existing safety behaviors.

Design (proposal):
- `SecurityInterceptor`:
  - `id`, `priority`
  - `check(action_request) -> (allow: bool, reason: str, audit_meta: dict)`
- SafetyKernel runs interceptors in order, first deny wins.
- Feature flag:
  - `QUENTIN_POLICY_INTERCEPTORS=1` enables chain mode.
- Optional HITL flag:
  - `QUENTIN_APPROVAL_GATE=1` enables approval gating when `ActionRequest.metadata.approval_required=true`.

Implementation Steps:
- [x] Add `quentin/kernel/interceptors/` with base + registry.
- [x] Wrap existing checks as interceptors:
  - [x] `path_traversal.py`
  - [x] `destructive_command.py`
- [x] Integrate interceptor chain into `SafetyKernel.guard_action`.
- [x] Add sync-compatible approval backend (`quentin/infra/security/approval.py`) and wire into `SafetyKernel.guard_action` behind `QUENTIN_APPROVAL_GATE=1`.
- [x] Tests:
  - [x] `tests/manual/test_security_interceptors_smoke.py`.
  - [x] `tests/unit/test_approval_gatekeeper_and_safety_kernel.py`.

Acceptance Criteria:
- Adding a new interceptor requires adding a module + registration only.
- Audit metadata is stable and visible to runtime sensing.

Rollback:
- `QUENTIN_POLICY_INTERCEPTORS=0` uses legacy SafetyKernel path.
