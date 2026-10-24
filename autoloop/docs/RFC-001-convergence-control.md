# RFC-001: AutoLoop Convergence Control System

## Status

- Draft: Implementable
- Owner: Lead / Integrator
- Scope: `autoloop/app/**`, `autoloop/tests/**`, `autoloop/templates/**`, `autoloop/schemas/**`

## Problem Statement

当前 AutoLoop 的主要问题不是单个 agent 能力不足，而是系统完成定义错误：

- workflow 走完会被标记为成功
- result 文件存在会被标记为成功
- 测试通过会被标记为成功

但这三者并不等于“目标代码升级成功”。

实际缺陷包括：

- control plane 与 data plane 混淆
- SSOT 不强，规则散落在 prompt 和 markdown prose
- acceptance gate 晚于任务完成判定
- `phases/*` 产物与真实代码 diff 脱钩
- 无结构化 retry / replan / rollback 路由
- traces、diff、tests、verdict 没有统一证据链
- session 恢复不是确定性主路径
- 缺少 anti-gaming 约束，agent 可以用低价值产物刷通过

## Goals

1. 重新定义 phase success，只允许“证据驱动成功”
2. 建立 schema-first 的唯一真相源
3. 将任务执行绑定到受控 workspace 和版本化 diff
4. 将 verifier / eval 前置为 phase gate
5. 建立可追溯 evidence graph
6. 将 retry / replan / rollback / human review 固化成 workflow 边

## Non-Goals

- 本 RFC 不要求切换具体模型供应商
- 本 RFC 不要求立即部署真实 Temporal 集群
- 本 RFC 不重写全部业务 agent prompt，仅要求 prompt 改为引用 schema

## Architecture

### 1. Spec Layer

唯一真相源由 3 个 schema 驱动：

- `TaskSpec`
  - 说明任务边界和上下文
- `ChangeSpec`
  - 说明允许修改的路径、符号、接口和禁止项
- `AcceptanceSpec`
  - 说明必须通过的测试、判定器、最小有效变更和回滚条件

schema 存放建议：

- `autoloop/schemas/task_spec.schema.json`
- `autoloop/schemas/change_spec.schema.json`
- `autoloop/schemas/acceptance_spec.schema.json`

### 2. Control Plane

control plane 只负责：

- workflow 编排
- checkpoint
- retry / replan / rollback / interrupt
- human approval
- workflow version 管理

control plane 不得直接宣称代码成功，只能宣称“流程推进状态”。

### 3. Workspace / Data Plane

每个任务绑定：

- `repo_root`
- `workspace_id`
- `base_sha`
- `head_sha`
- `worktree_path`

所有代码修改必须发生在受控 workspace 内。

禁止把以下文件作为“完成主证据”：

- `phases/*/results/*.md`
- `phases/*/phase_report.md`
- `runtime/logs/*`
- `runtime/hooks/*`

这些文件只能是辅助证据，不能替代真实 diff。

### 4. Verification Plane

验证顺序固定为：

1. schema validation
2. path allowlist / denylist validation
3. target symbol / interface hit validation
4. diff value validation
5. build / lint / unit tests
6. integration / replay / hidden tests
7. grader verdict
8. acceptance verdict

只有全部通过，phase 才能 promotion。

### 5. Evidence Plane

所有运行证据统一挂到 `EvidenceRecord`：

- `task_id`
- `workflow_version`
- `run_id`
- `thread_id`
- `base_sha`
- `head_sha`
- `changed_files`
- `diff_fingerprint`
- `test_run_ids`
- `grader_run_ids`
- `acceptance_verdict`

建议目录：

- `autoloop/runtime/evidence/<run_id>/`
- `autoloop/runtime/checkpoints/<run_id>/`

### 6. Recovery / Governance Plane

workflow 必须支持 4 条恢复边：

- `retry_same_plan`
- `replan_from_spec`
- `rollback_via_compensation`
- `escalate_to_human`

任何 failure 不能只写日志后继续向后推进。

## Canonical Status Model

必须拆分以下状态：

- `orchestration_status`
  - `pending | running | blocked | failed | completed`
- `execution_status`
  - `not_started | in_progress | diff_created | tests_failed | tests_passed | rolled_back`
- `acceptance_status`
  - `not_evaluated | rejected | conditionally_passed | passed`

最终 phase 是否成功，仅看：

- `acceptance_status == passed`

## Required Typed Contracts

### TaskSpec

关键字段：

- `task_id`
- `phase_id`
- `module_id`
- `requirement_ids`
- `workspace_id`
- `repo_root`
- `worktree_path`
- `input_artifacts`
- `output_artifacts`
- `priority`
- `risk_level`

### ChangeSpec

关键字段：

- `change_id`
- `task_id`
- `allowed_paths`
- `forbidden_paths`
- `required_files`
- `required_symbols`
- `forbidden_symbols`
- `min_effective_diff_lines`
- `must_update_tests`

### AcceptanceSpec

关键字段：

- `acceptance_id`
- `task_id`
- `required_tests`
- `required_graders`
- `required_artifacts`
- `hidden_test_group`
- `rollback_on_failure`
- `human_review_required`

## Workflow Edges

主路径：

1. `spec_ready`
2. `workspace_prepared`
3. `task_dispatched`
4. `diff_generated`
5. `verification_running`
6. `acceptance_decided`
7. `phase_promoted`

失败路径：

1. `schema_invalid -> replan_from_spec`
2. `no_effective_diff -> rejected`
3. `path_violation -> rollback_via_compensation`
4. `tests_failed -> retry_same_plan`
5. `retries_exhausted -> escalate_to_human`

## Anti-Gaming Policy

必须实现以下硬门禁：

1. diff 未命中目标白名单路径，直接拒绝
2. diff 未命中目标符号 / 接口，直接拒绝
3. 只改 docs / logs / results 文件，不得判成功
4. 未达到最小有效变更阈值，不得判成功
5. 公开测试通过但隐藏测试失败，不得判成功
6. grader 与 test verdict 冲突时，进入人工复核
7. 已知 exploit 样本必须进入 replay set

## Session Reliability

session 只能是 workflow 的优化层，不能是 correctness 的依赖项。

要求：

- session 恢复失败时可降级到无 session 模式
- state 恢复必须由 append-only event log 支撑
- session warning 不能默默吞掉，必须进入 evidence
- replay test 必须覆盖 state migration 和 resume fallback

## Proposed Directory Layout

```text
autoloop/
  app/
    contracts/
      task_spec.py
      change_spec.py
      acceptance_spec.py
      evidence.py
    control/
      workflow_status.py
      gate_engine.py
      recovery_router.py
    workspace/
      workspace_manager.py
      diff_inspector.py
      target_guard.py
    verification/
      verifier.py
      test_runner.py
      grader_runner.py
      acceptance_engine.py
    evidence/
      evidence_store.py
      trace_linker.py
  schemas/
    task_spec.schema.json
    change_spec.schema.json
    acceptance_spec.schema.json
    evidence_record.schema.json
  tests/
    unit/
    integration/
    replay/
    acceptance/
```

## Rollout Phases

### Phase 1: Completion Semantics

- 拆分三层状态
- 调整 phase success 判定
- 禁止 `results/*.md` 作为唯一成功依据

### Phase 2: Schema-First Contracts

- 引入 `TaskSpec` / `ChangeSpec` / `AcceptanceSpec`
- 任务分发与结果收集改为 schema 驱动

### Phase 3: Workspace Binding

- 每任务绑定 `repo_root/base_sha/head_sha/worktree_path`
- 建立 diff 采集与 path guard

### Phase 4: Verification Gates

- 前置 verifier
- 引入 diff value 和 hidden tests

### Phase 5: Recovery and Evidence

- 实现 retry / replan / rollback / human review
- 打通 evidence graph

## Exit Criteria

本 RFC 视为落地完成，必须满足：

- phase 成功定义已切换到 `acceptance_status`
- 新任务必须带 `TaskSpec` / `ChangeSpec` / `AcceptanceSpec`
- 任何 run 都能追溯到 `base_sha -> diff -> tests -> verdict`
- 至少存在 1 组 anti-gaming integration tests
- 至少存在 1 组 replay tests 证明恢复链可用
