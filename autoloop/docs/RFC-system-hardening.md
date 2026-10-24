# RFC · AutoLoop System Hardening (Agent System Engineering)

## 1. Objective
- 目标不是修某次任务结果，而是提升 AutoLoop 在任意任务上的**收敛稳定性、可观测性、可恢复性**。
- 完成定义：同类失败在后续 run 中被系统机制吸收，而不是重复出现。

## 2. Non-Goals
- 不针对某个业务模块（如 `module_main`）做功能优化。
- 不以“单轮跑通”作为成功标准。

## 3. System Problems (Root Categories)
- **Contract Drift**：任务描述、输出契约、验收门禁之间不一致。
- **Routing Blindness**：失败后回路（retry/replan/escalate）缺少可解释路由条件。
- **Weak Recovery**：human/auto review 决议未结构化注入，导致重复失败。
- **Observability Gaps**：高层通过/失败无法映射到首错阶段与责任主体。
- **Evaluation Fragility**：策略改动缺少回放回归，易引入退化。

## 4. Target Architecture
1. **Policy Plane**
   - 版本化策略文件（auto-review、gate mapping、risk policy）。
   - 每次决策记录 `policy_version`。
   - 支持 `calibrate-auto-review-policy` 基于 evidence 自动微调 profile 与阈值。
2. **Control Plane**
   - 有限状态 + 失败签名熔断 + replan 升级。
   - 默认 auto-review，低置信才人工。
   - `failure_router_policy` 将 `first_failure_stage` 映射为统一 recovery action。
3. **Contract Plane**
   - 强制 typed contracts；关键字段条件校验（如 reviewer finding_codes）。
4. **Recovery Plane**
   - resolution -> machine-readable repair constraints -> task injection。
5. **Evidence Plane**
   - 首错阶段、责任 agent、失败签名、风险信号全链路落盘。
6. **Replay Plane**
   - 历史失败样本回放包，作为每次改动的回归门禁。

## 5. Invariants (Must Hold)
- `phase completed` iff `acceptance_status == passed`。
- `needs_revision` reviewer 输出必须包含 `finding_codes`。
- `human_review_required` 产生后，必须存在可追溯 resolution 或明确未决状态。
- 相同 `failure_signature` 不可无限 `retry_same_plan`。

## 6. Rollout Plan
### Phase A: Control Reliability
- 默认 auto-review control flow + max auto-resume guard。
- failure-signature 熔断统一函数化。

### Phase B: Contract Strictness
- 强制 reviewer 条件字段。
- required_tests 从“执行”升级到“执行且成功”映射判定。

### Phase C: Recovery Injection
- resolution 注入 machine-readable constraints。
- 所有 agent 任务模板统一消费约束块。

### Phase D: Replay Governance
- 建立 replay pack（失败/结构风险/通过样本）。
- 将 replay 纳入 CI gate。

## 7. Metrics
- `auto_review_decision_rate`（approved/rejected）
- `auto_resume_success_rate`
- `repeat_failure_signature_rate`
- `time_to_first_clear_failure_owner`
- `manual_intervention_rate`
- `failure_stage_distribution`
- `failure_owner_distribution`

## 8. Acceptance
- 连续 3 次系统改动后 replay pack 全绿。
- 同一失败签名重复率下降（基线后至少 30%）。
- 人工介入率下降且无风险放大（以 failed grader/structural codes 不上升为约束）。
