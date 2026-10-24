# AutoLoop Convergence Test Plan

## Test Strategy

测试目标不是证明 workflow 会跑，而是证明系统会拒绝低价值成功，并且能够把真实代码升级和证据链绑定起来。

## Test Layers

### 1. Unit Tests

验证最小规则单元：

- schema validation
- status transitions
- path allowlist / denylist
- target symbol hit detection
- effective diff scoring
- acceptance decision table
- session health classification

### 2. Integration Tests

验证跨模块行为：

- task dispatch with typed contracts
- workspace binding with git root
- verifier gate before phase complete
- docs-only diff rejection
- hidden tests failure rejection
- retry / replan / rollback routing

### 3. Replay Tests

验证可恢复性：

- run checkpoint replay
- session fallback replay
- state migration replay
- exploit replay set

### 4. Acceptance Tests

验证用户关心的最终性质：

- 非目标改动不能过
- 文档补丁不能冒充代码升级
- 所有成功 run 都有 diff + tests + verdict
- 失败 run 能进入结构化恢复分支

## Required Test Files

- `tests/unit/test_workflow_status.py`
- `tests/unit/test_contract_schemas.py`
- `tests/unit/test_workspace_binding.py`
- `tests/unit/test_target_guard.py`
- `tests/unit/test_verifier.py`
- `tests/unit/test_evidence_store.py`
- `tests/unit/test_session_health.py`
- `tests/integration/test_phase_success_requires_acceptance.py`
- `tests/integration/test_docs_only_diff_rejected.py`
- `tests/integration/test_non_target_diff_rejected.py`
- `tests/integration/test_hidden_test_failure_blocks_phase.py`
- `tests/integration/test_recovery_routes.py`
- `tests/integration/test_evidence_chain.py`
- `tests/replay/test_resume_fallback.py`
- `tests/replay/test_checkpoint_replay.py`
- `tests/replay/test_known_exploit_replays.py`
- `tests/acceptance/test_real_upgrade_requires_target_diff.py`
- `tests/acceptance/test_phase_success_requires_evidence_chain.py`

## Critical Scenarios

### Scenario A: Docs-Only Fake Success

前置：

- task 目标要求修改 `app/**`

动作：

- dev 只修改 docs / result files

期望：

- verifier 返回 `rejected`
- `acceptance_status != passed`

### Scenario B: Wrong Path Diff

前置：

- `allowed_paths = ["app/control/**"]`

动作：

- 改动落在 `README.md`

期望：

- path guard 拒绝
- phase 不得完成

### Scenario C: Tests Green but Hidden Tests Red

前置：

- 公开测试通过
- 隐藏测试失败

期望：

- acceptance engine 拒绝 promotion

### Scenario D: Resume Warning

前置：

- session 触发 `state_db falling_back`

期望：

- warning 记录进 evidence
- 可切换到 no-session 模式继续执行

### Scenario E: Replayability

前置：

- run 产生 checkpoint

动作：

- 从 checkpoint 重放

期望：

- 同一输入生成同一 status 路径
- evidence graph 不丢失关键主键

## Exit Test Suite

发布前必须至少通过：

1. 全部 unit tests
2. 全部 integration tests
3. replay 套件中的恢复与 exploit replay
4. acceptance tests 中的 2 个关键真实场景

## Metrics To Track

- false positive rate
- docs-only rejection count
- non-target diff rejection count
- acceptance rejection count
- retry success rate
- rollback success rate
- resume fallback count
