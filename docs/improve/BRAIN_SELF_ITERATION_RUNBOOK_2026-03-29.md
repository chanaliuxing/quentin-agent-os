# Brain Self-Iteration Runbook (2026-03-29)

## 1. 目标
- 把“大脑可跑”升级成“可持续迭代、可量化验收”。
- 每次迭代都必须留下证据：命令、报告、通过/失败结论。

## 2. 迭代节奏
- 每日最少 2 次 gate：
  - 离线稳定 gate（`offline-smoke`）
  - 在线真实 gate（真实模型，不开 `offline-smoke`）
- 每周 1 次回归复盘：
  - 汇总失败模式 TopN
  - 调整一个策略（只改一个主变量）
  - 重新基线一次 SLO

## 3. 一键 Gate 命令
### 3.1 离线稳定 Gate（必须）
```bash
.venv/bin/python scripts/run_brain_self_iteration_gate.py --offline-smoke
```

### 3.2 在线真实 Gate（必须）
```bash
.venv/bin/python scripts/run_brain_self_iteration_gate.py
```

### 3.3 高标准 Gate（可选）
```bash
.venv/bin/python scripts/run_brain_self_iteration_gate.py --strict-done
```

## 4. Gate 判定规则
- Pass 条件（默认）：
  - `check_champion_env` 通过
  - `check_champion_runtime` 通过
  - `canary_brain_once` 正常退出（exit code 0）
- `--strict-done` 附加条件：
  - canary 报告中 `Done=True`

## 5. 报告与证据
- Gate 报告：
  - `data/landing/brain_self_iteration_gate_report.json`
- Canary 运行证据：
  - `data/audit_events.jsonl`
  - `data/traces/events.jsonl`

## 6. TODO（从大骨架到小骨架）
### P0 稳定性（先完成）
- [x] 主流程 canary 不再卡死（session/lane 嵌套问题修复）
- [x] `offline-smoke` 一键入口（`run_canary_brain_once.py --offline-smoke`）
- [x] 自我迭代 gate 脚本（`run_brain_self_iteration_gate.py`）
- [ ] 在线真实 gate 连续 7 天通过率 >= 99%

### P1 质量
- [ ] `Done=True` 周均 >= 80%（在线真实 gate）
- [ ] `Done=True` 周均 >= 90%（目标）
- [ ] Top3 失败模式（超时/工具误用/低置信）各自下降 >= 50%

### P2 性能/SLO
- [ ] 关键链路 p95 达标（按当前 SLO 文件）
- [ ] canary 超时率 < 1%
- [ ] 自动恢复成功率 >= 95%

### P3 发布可靠性
- [ ] 通过 gate 才允许进入 canary 流量
- [ ] 失败自动冻结候选策略并记录 rollback 证据
- [ ] 形成每周“策略变更 -> 指标变化”审计报告

## 7. 验收标准（DoD）
- DoD-1: 离线 gate 连续 50 次全绿，无人工干预。
- DoD-2: 在线 gate 连续 7 天通过率 >= 99%，且无 P0 卡死。
- DoD-3: 在线场景 `Done=True` 稳定 >= 90%，并保留完整 trace 证据。
- DoD-4: 每个失败模式都有对应回归用例，并在 CI 可复跑。
