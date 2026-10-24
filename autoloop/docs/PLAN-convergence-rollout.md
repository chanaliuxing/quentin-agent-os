# AutoLoop Convergence Rollout Plan

## Objective

把 AutoLoop 从“session-driven agent loop”升级为“schema-driven convergence system”。

## Phase Plan

### Phase 0: Baseline and Freeze

目标：

- 固定当前成功定义、日志结构、phase 输出格式
- 记录当前已知假阳性路径

输入：

- 当前 `app/main.py`
- 当前 `app/temporal/activities.py`
- 当前 `tests/unit/test_phase_report_summary.py`

输出：

- baseline run report
- false positive catalog
- current state transition map

风险：

- baseline 不准确会污染后续对比

### Phase 1: Completion Semantics Refactor

目标：

- 引入 `orchestration_status`
- 引入 `execution_status`
- 引入 `acceptance_status`
- 改写 phase report summary

输入：

- baseline artifacts
- 当前 phase/report 逻辑

输出：

- 新状态模型
- phase gate 判定逻辑
- 兼容旧报告的 adapter

依赖：

- Phase 0 完成

### Phase 2: Schema-First Tasking

目标：

- 将任务分发从 markdown prose 切换到 typed contract
- 保留 markdown 只作为 agent-readable view

输入：

- RFC 定义的 3 个核心 schema

输出：

- `TaskSpec` contract
- `ChangeSpec` contract
- `AcceptanceSpec` contract
- schema validation pipeline

依赖：

- Phase 1 完成

### Phase 3: Workspace and Diff Governance

目标：

- 每任务绑定真实 repo root 和 worktree
- 建立 diff path guard 和 target guard

输入：

- git top-level
- base/head sha
- allowlist / denylist

输出：

- workspace manager
- diff inspector
- effective diff scorer

依赖：

- Phase 2 完成

### Phase 4: Verification-First Gates

目标：

- verifier 前置
- 增加 hidden tests
- 增加 grader runner

输入：

- ChangeSpec
- AcceptanceSpec

输出：

- verifier engine
- hidden test contract
- acceptance engine

依赖：

- Phase 3 完成

### Phase 5: Recovery and Evidence Graph

目标：

- 建立 retry / replan / rollback / human review 路由
- 建立 evidence graph

输入：

- 所有前置状态和验证产物

输出：

- recovery router
- evidence record store
- replayable checkpoints

依赖：

- Phase 4 完成

## Milestones

### Milestone A

- false positive 无法再由 docs-only diff 通过

### Milestone B

- 所有任务都有 typed contracts

### Milestone C

- 所有成功 run 都能追溯到 base/head sha 和 test evidence

### Milestone D

- 失败 run 能自动进入 retry / replan / rollback 其中之一

## Delivery Order

1. 先做状态语义
2. 再做 schema
3. 再做 workspace 绑定
4. 再做 verifier gate
5. 最后做 recovery 和 evidence

## Rollout Risks

- 旧测试依赖旧成功定义
- 旧 prompt 会绕过 schema 规则
- worktree 集成可能暴露更多 git 根路径问题
- hidden tests 设计不当会制造误杀

## Risk Controls

- 每 phase 保留 compatibility adapter
- 所有 gate 先以 warn 模式上线，再切 hard fail
- 每 phase 都保留 replay fixtures
- 所有 breaking changes 必须配迁移说明
