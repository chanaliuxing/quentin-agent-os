# OpenClaw 能力借鉴落地方案（Quentin 大脑）

日期：2026-02-10  
范围：`quentin/`、`meta_agent/`、`scripts/`、`tests/`

## 1. 目标与原则

目标：把 OpenClaw 中已验证的工程能力，按“低风险可回滚、先核心后扩展”的方式落地到 Quentin 大脑主链路。

原则：
- 先做 P0 防护与稳定性，再做 P1 体验与效率，再做 P2 扩展能力。
- 复用 Quentin 现有机制，不做大规模推倒重来。
- 每项改动都要求 DoD（Definition of Done）和最小测试闭环。

## 2. 基线现状（代码审计）

已具备：
- 会话串行车道：`quentin/infra/concurrency/lanes.py`
- API 入口串行化：`meta_agent/api/server.py`
- Session Delta 节流写入：`quentin/memory/session_deltas.py`
- 系统事件队列：`quentin/runtime/system_events.py`
- 自编程沙箱测试：`meta_agent/self_programming/test_runner.py`
- SOP 雏形（Markdown）：`quentin/skills/manager.py`

主要缺口：
- 无统一外部内容防注入包装（Lead-Shielding）。
- 缺统一 wake 回调协议（后台任务结束主动唤醒）。
- 技能体系仍以 JSON 为主，缺 SKILL.md 触发与懒加载协议。
- 自编程工作区隔离不彻底（仍在当前 repo branch 上操作）。
- 交互式命令能力被策略性禁用，缺受控 PTY 通道。

## 3. 分阶段实施

## P0（本周）安全与一致性

P0-1 外部内容防辐射包装（Lead-Shielding）
- 新增 `quentin/security/external_content.py`。
- 实现：
  - `wrap_external_content(...)`
  - marker 转义与闭合防逃逸
  - 可疑注入模式检测（仅告警，不自动执行）
- 接入点：
  - `meta_agent/research/tool.py`
  - `meta_agent/tools/browser/playwright_tool.py`
  - 其他 web/search/fetch 输出链路
- DoD：任意外部文本进入 LLM 前都能被统一包装。

P0-2 全域 Session Lane 统一入口
- 审计所有运行入口，统一经 `enqueue(..., global_lane="main")`。
- 重点：
  - CLI `qctl run-task` 路径
  - daemon 队列执行路径
  - patchflow/self-programming 触发入口
- DoD：同 session 的并发请求不出现状态写入乱序。

P0-3 Wake 回调最小闭环
- 新增命令：`python -m quentin.cli.qctl wake --session-id ... --text ...`
- 行为：
  - 写入 `SystemEventQueue.enqueue_event(...)`
  - 标准 event_type：`background_task_done`
- DoD：后台任务可通过单行 CLI 回调“唤醒”主会话。

## P1（两周）技能协议与工作区隔离

P1-1 SKILL.md 协议化（混合制）
- 保留 JSON registry（治理、指标、状态）。
- 新增 markdown skill loader：
  - 目录规范：`quentin/mutable/skills/<skill_id>/SKILL.md`
  - frontmatter 字段：`name`、`description`、`requires`、`triggers`
  - 按需懒加载，不全量注入上下文
- DoD：模型可先识别技能，再按需读取 SKILL.md 正文。

P1-2 自编程物理隔离
- 新增工作区策略：`mktemp -d` + `git clone --depth 1` 或 `git worktree`
- 自编程和 CR 任务默认在临时工作区执行。
- 仅产出 patch/report 回写主仓库，不直接在主工作区跑高风险命令。
- DoD：异常任务不会污染主仓库状态。

P1-3 自编程安全边界强化
- `target_file` allowlist 上移到统一策略层（非仅 deterministic）。
- 补充 path guard、敏感路径 denylist、repo root 越界检测。
- DoD：跨目录误写与越权写入被硬性阻断。

## P2（三周）受控 PTY 与后台编排

P2-1 新增受控 PTY 工具
- 保留现有 `shell.run_command` 非交互策略不变。
- 新增 `shell.interactive_session`（feature flag 默认关闭）。
- 能力：
  - 启动 PTY session
  - write/poll/log/kill
  - 强审计 + 强策略门禁
- DoD：需要验证码/y/n 的命令可在受控场景运行。

P2-2 背景任务编排协议
- 定义统一后台任务结构：session_id、task_id、timeout、wake 文案。
- 融合 `SystemEventQueue`，对 UI/API 输出结构化进度状态。
- DoD：长任务“可观察、可中断、可回调”。

## 4. 技术设计要点

外部内容包装：
- 包裹格式采用高罕见 marker + 明确安全前置提示。
- 对 marker 注入尝试做文本净化，不允许提前闭合。

技能协议：
- Skill 触发依赖简短描述，不在主提示词注入大段 body。
- 详细步骤只在命中 skill 时加载，减少 token 压力。

隔离策略：
- “逻辑隔离（git branch）+ 物理隔离（临时工作区）”双层防线。
- 默认优先物理隔离，branch 仅作为二级保险。

PTY 边界：
- 只开放白名单命令。
- 强制 session 级审计和最大时长限制。
- prod 环境默认禁用。

## 5. 里程碑与验收

M1（P0 完成）：
- 外部内容包装上线
- wake 回调可用
- lane 入口统一

M2（P1 完成）：
- SKILL.md 混合协议上线
- 自编程临时工作区隔离上线

M3（P2 完成）：
- 受控 PTY 上线
- 后台任务编排与唤醒链路稳定

## 6. 回滚策略

- 全部新增能力挂 feature flag。
- 出现异常可逐项关闭：
  - `QUENTIN_EXTERNAL_CONTENT_SHIELD=false`
  - `QUENTIN_SKILL_MD_ENABLED=false`
  - `QUENTIN_SELFPROG_ISOLATED_WORKDIR=false`
  - `QUENTIN_INTERACTIVE_SHELL_ENABLED=false`

## 7. 风险清单

- 过度包装导致召回噪声上升。
- SKILL.md 触发不准导致上下文漂移。
- 临时工作区复制开销导致时延增加。
- PTY 权限边界未锁紧引发执行风险。

对应控制：
- 逐步灰度 + 指标观测（成功率、时延、失败原因）。
- 强化单测/集成测试与审计日志。
