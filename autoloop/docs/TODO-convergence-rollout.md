# AutoLoop Convergence TODO

## Lead / Integrator

- 定义 `phase success = acceptance passed` 的统一规则
- 审核 `TaskSpec` / `ChangeSpec` / `AcceptanceSpec` 字段
- 决定 `warn -> fail` 的 gate 切换时机
- 维护 migration checklist

Done Definition:

- phase report 不再仅凭 result 文件判绿
- 所有核心 schema 有版本号和迁移策略

## Control Plane Agent

- 新增 `workflow_status.py`
- 为 phase 和 module 建立三层状态
- 改写 state transition table
- 为失败场景接入 `retry_same_plan` / `replan_from_spec` / `rollback_via_compensation` / `escalate_to_human`

Outputs:

- `app/control/workflow_status.py`
- `app/control/recovery_router.py`
- `tests/unit/test_workflow_status.py`
- `tests/integration/test_recovery_routes.py`

## Spec Agent

- 定义 `TaskSpec` Pydantic model 与 JSON Schema
- 定义 `ChangeSpec` Pydantic model 与 JSON Schema
- 定义 `AcceptanceSpec` Pydantic model 与 JSON Schema
- 建立 markdown view renderer

Outputs:

- `app/contracts/task_spec.py`
- `app/contracts/change_spec.py`
- `app/contracts/acceptance_spec.py`
- `schemas/task_spec.schema.json`
- `schemas/change_spec.schema.json`
- `schemas/acceptance_spec.schema.json`
- `tests/unit/test_contract_schemas.py`

## Workspace Agent

- 解析 git top-level
- 为每 task 绑定 `repo_root/base_sha/head_sha/worktree_path`
- 实现 path allowlist / denylist
- 实现 target symbol hit 检测
- 实现 effective diff scoring

Outputs:

- `app/workspace/workspace_manager.py`
- `app/workspace/diff_inspector.py`
- `app/workspace/target_guard.py`
- `tests/unit/test_workspace_binding.py`
- `tests/unit/test_target_guard.py`

## Verification Agent

- 实现 verifier pipeline
- 实现 hidden test contract
- 实现 grader runner
- 实现 acceptance engine

Outputs:

- `app/verification/verifier.py`
- `app/verification/test_runner.py`
- `app/verification/grader_runner.py`
- `app/verification/acceptance_engine.py`
- `tests/unit/test_verifier.py`
- `tests/integration/test_acceptance_engine.py`

## Evidence Agent

- 定义 `EvidenceRecord`
- 采集 diff、tests、grader、verdict
- 将 trace id / run id / workflow version 绑定到 evidence
- 提供 phase evidence summary

Outputs:

- `app/evidence/evidence_store.py`
- `app/evidence/trace_linker.py`
- `schemas/evidence_record.schema.json`
- `tests/unit/test_evidence_store.py`
- `tests/integration/test_evidence_chain.py`

## Anti-Gaming Agent

- 建立 docs-only diff 拒绝规则
- 建立 non-target-path diff 拒绝规则
- 建立 min effective diff threshold
- 建立 exploit replay set

Outputs:

- `app/verification/policies.py`
- `tests/integration/test_docs_only_diff_rejected.py`
- `tests/integration/test_non_target_diff_rejected.py`
- `tests/replay/test_known_exploit_replays.py`

## Session / Reliability Agent

- 记录 `state_db falling_back` 告警为结构化证据
- session 恢复失败时切换 no-session 模式
- 引入 checkpoint compatibility tests
- 增加 deterministic replay tests

Outputs:

- `app/runners/session_health.py`
- `tests/unit/test_session_health.py`
- `tests/replay/test_resume_fallback.py`
- `tests/replay/test_checkpoint_replay.py`

## Documentation Agent

- 更新 README 的成功定义和运行方式
- 更新 AGENTS 使用方式，要求 prompt 引用 schema
- 编写 migration guide

Outputs:

- `README.md`
- `AGENTS.md`
- `docs/MIGRATION-convergence.md`

## Cross-Cutting TODO

- 每个 phase 增加 compatibility adapter
- 每个 phase 增加 rollback note
- 每个 phase 增加 observability field additions
- 每个 phase 都要有 acceptance checklist
