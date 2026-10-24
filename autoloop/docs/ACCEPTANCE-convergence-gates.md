# AutoLoop Convergence Acceptance Criteria

## Acceptance Model

AutoLoop 只有在以下三类证据同时成立时，才能把一次升级判为成功：

1. 有受控 workspace 上的目标 diff
2. 有可复现测试和 grader 证据
3. 有 `acceptance_status=passed`

## Phase Acceptance Gates

### Gate A: Completion Semantics

通过标准：

- phase report 使用三层状态
- `results/*.md` 不能单独导致 phase 变绿
- docs-only run 被标记失败

拒绝条件：

- workflow completed 但 acceptance 未判定
- execution 没有 diff 仍显示成功

### Gate B: Schema-First Tasking

通过标准：

- 每个新任务都生成 `TaskSpec`
- 每个执行任务都生成 `ChangeSpec`
- 每个验收任务都生成 `AcceptanceSpec`
- agent prompt 明确引用 schema id

拒绝条件：

- 任务只存在 prose，没有 schema
- schema 字段缺失 allowlist / tests / forbidden paths

### Gate C: Workspace Binding

通过标准：

- 每个 run 都可解析 `repo_root`
- 每个任务都记录 `base_sha/head_sha`
- 每个任务都能追溯到 `worktree_path`

拒绝条件：

- 结果文件存在但没有 git identity
- 无法确定改动发生在哪个 workspace

### Gate D: Verification First

通过标准：

- verifier 在 phase complete 之前执行
- 路径校验、目标命中校验、测试校验全部落地
- hidden tests 和 grader verdict 都进入 evidence

拒绝条件：

- phase 先完成后验证
- 仅 public tests 通过即放行

### Gate E: Recovery and Evidence

通过标准：

- 失败 run 会进入 retry / replan / rollback / human review 之一
- run 具备完整 evidence chain
- replay tests 可重放关键路径

拒绝条件：

- failure 只写日志不跳转
- evidence 缺少 `base_sha` 或 `test_run_id`

## Run-Level Acceptance Checklist

每个真实 run 必须回答以下问题，且答案可机检：

1. 本次任务的 `task_id` 是什么
2. 对应 `requirement_ids` 是什么
3. 改动发生在哪个 `repo_root/worktree_path`
4. `base_sha/head_sha` 是什么
5. 命中了哪些目标文件和目标符号
6. 跑了哪些 tests / graders
7. 是否触发 hidden tests
8. 最终 acceptance verdict 是什么
9. 若失败，进入了哪条恢复边

## Anti-False-Positive Acceptance

以下情况必须统一判失败：

- 只改文档、日志、结果文件
- 未命中目标路径
- 未命中目标符号
- 未达到最小有效变更
- 没有测试证据
- 没有 evidence chain
- acceptance 未显式通过

## Release Acceptance

该收敛系统视为可用，至少要满足：

- docs-only fake success 被稳定拦截
- target diff 缺失无法通过 acceptance
- 成功 run 100% 可追溯到 diff 与 test evidence
- replay 测试通过
- session fallback 不再导致 run 状态丢失
