# AutoLoop 架构设计（Lead 视角）

## 1) Agent 通信协议（文件即总线）

- **任务输入**：`autoloop/phases/phase_xx/tasks/<agent>.md`
- **结果输出**：`autoloop/phases/phase_xx/results/<agent>.md`
- **生命周期 hook**：`autoloop/runtime/hooks/*.json`
- **运行日志**：`autoloop/runtime/logs/phase_xx_<agent>.log`

通信约束：

1. 子 agent 只读取自己的 task 文档，不读别的 agent 任务。
2. 子 agent 只能写自己的 result 文档。
3. Lead 只在 `phase_xx_all_agents_done` hook 出现后进行集成。
4. session_id 与 workdir 必须一一绑定，冲突直接失败。

当前 agent 拆分（按 Quentin 架构）：

- memory / planning / execution / tools / protocol / safety / learning
- 其中 `memory` 固定旧 session（保留历史记忆），其他 agent 可自动创建新 session

## 2) 进程控制

- 启动命令：`codex exec resume <session_id> "<prompt>" --json ...`
- 每个 agent 在独立工作目录执行：`worktrees/<agent>-agent`
- 每个 agent 独立进程，支持超时（默认 5400s）
- 超时后 Lead 对子进程组发送 `SIGTERM`，必要时升级到 `SIGKILL`
- 无任务 agent 不启动，只写 `skipped` 结果
- 失败 agent 自动重试（默认 2 次），也支持 `rerun-failed`

## 3) Resume 机制与风险

已验证 `codex exec resume` 可以恢复你提供的 session（memory agent）并返回结果。

发现的风险：

1. **state_db record_discrepancy 警告**
   - 现象：CLI 输出 `find_thread_path_by_id_str_in_subdir, falling_back`
   - 影响：通常不阻断执行，但说明本地 thread 索引与目录状态有漂移
   - 建议：定期清理/重建 Codex 本地 state 索引

2. **长会话上下文膨胀**
   - 现象：resume 后 input token 非常大
   - 影响：成本上升、响应波动
   - 建议：阶段性 fork 新 session，保留旧 session 仅做历史索引

3. **prompt 约束漂移**
   - 现象：同一 session 会继承历史行为
   - 影响：新 phase 可能执行额外动作
   - 建议：每次 phase prompt 强制写明“只处理 task.md 列表”

4. **模型版本不一致告警**
   - 现象：resume 时提示 session recorded model 与当前模型不一致
   - 影响：行为可能漂移
   - 建议：在 config 里给该 agent 固定 `model`，或统一重建该 session

## 4) Git 协作与冲突治理

- 约束每个 agent commit message 包含 `agent:<name>`
- 每个 agent 使用独立分支：`agent/<name>`（git worktree）
- phase 结束自动 merge 到 `integration/autoloop`
- Lead 在 phase 结束后生成 overlap 报告：
  - 同文件被多个 `agent:*` commit 触达 => 标记为 merge 风险
- Lead 决策：
  1. 先保留主路径可运行版本
  2. 再做功能合并（必要时手工整合）
  3. 重新跑架构门禁与测试

## 5) 当前实现边界

当前脚本已实现：

- Blueprint -> 多 phase -> 多 agent 任务拆分
- Task/Result/Hook 文件协议
- Resume 派发、超时收敛、日志落盘
- Phase 后验证命令和 overlap 报告

后续可增强：

- 自动读取 result.md 生成下一 phase“回归/补丁”任务
- 引入失败重试策略（仅重跑失败 agent）
- 基于结果自动降低/提升每 agent phase 任务量
