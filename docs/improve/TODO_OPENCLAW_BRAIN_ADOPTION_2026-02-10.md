# TODO：OpenClaw 借鉴能力落地执行清单（Quentin）

日期：2026-02-10  
状态：`[ ]` 未开始 / `[~]` 进行中 / `[x]` 完成

## A. P0 安全与稳定（优先级最高）

[x] A1 新增外部内容防注入包装模块
- 目标文件：`quentin/security/external_content.py`
- 任务：
  - 实现 `wrap_external_content(content, source, sender=None, subject=None, include_warning=True)`
  - 实现 marker 转义函数（防止提前闭合）
  - 实现 `detect_suspicious_patterns(content)`（告警用途）
- DoD：
  - 单测覆盖 marker 注入、正常内容、空文本
  - 返回格式稳定，含 source 元数据
- 测试：
  - `pytest tests/unit/test_external_content_shield.py -q`
- 预计：0.5d

[x] A2 在 web/research 链路接入包装
- 目标文件：
  - `meta_agent/research/tool.py`
  - `meta_agent/tools/browser/playwright_tool.py`
  - 其他 web fetch/search 返回路径
- 任务：
  - 在送入 LLM 前统一调用 `wrap_external_content`
  - 加 feature flag：`QUENTIN_EXTERNAL_CONTENT_SHIELD`
- DoD：
  - 开启 flag 时，LLM 输入均含外部内容边界
  - 关闭 flag 时行为与当前一致
- 测试：
  - `pytest tests/unit/test_research_interface_v3.py -q`
  - 新增 `tests/unit/test_external_content_shield_integration.py`
- 预计：0.5d

[x] A3 全域 Session Lane 入口审计与补齐
- 目标文件：
  - `meta_agent/api/server.py`
  - `quentin/cli/qctl.py`
  - `quentin/runtime/brain_daemon.py`
  - 其他 task 入口
- 任务：
  - 统一使用 `resolve_session_lane` + `enqueue`
  - 对无 session_id 的入口定义默认 lane 规则
- DoD：
  - 同 session 并发任务执行顺序稳定
  - 无写入乱序回归
- 测试：
  - `pytest tests/integration/test_task_source_obs.py -q`
  - 新增并发回归测试 `tests/unit/test_brain_daemon_session_lane.py`
- 预计：1d

[x] A4 实现 Wake 回调最小闭环
- 目标文件：
  - `quentin/cli/qctl.py`
  - `quentin/runtime/system_events.py`
- 任务：
  - 增加 `qctl wake` 子命令
  - 参数：`--session-id`、`--text`、`--event-type`（默认 `background_task_done`）
- DoD：
  - 手动执行 wake 后，事件可被 `drain_events` 拉取
- 测试：
  - 新增 `tests/unit/test_qctl_wake.py`
  - `pytest tests/unit/test_qctl_wake.py -q`
- 预计：0.5d

## A+. P0-Extension 工具/技能可插拔平台（优先级：高）

[x] A+1 工具插件 manifest + loader（新增文件即可扩展工具）
- 目标文件：
  - `quentin/tools/plugin_loader.py`
  - `quentin/tools/plugin_schema.py`
  - `quentin/tools/plugin_cache.py`
- DoD：
  - 在 `extensions/tools/<id>/` 放入 `manifest.yaml` + `logic.py` 即可被自动注册
- 测试：
  - `pytest tests/unit/test_tool_plugin_loader.py -q`

[x] A+2 启动期自动扫描并挂载到 ToolManager
- 目标文件：`quentin/bootstrap/container.py`
- DoD：Container 初始化 ToolManager 时自动注册插件工具

[x] A+3 ToolManager 注册工具时同步支持 normalized key
- 目标文件：`quentin/tools/manager.py`
- DoD：`plugin.echo` 与 `plugin_echo` 调用均可命中相同 handler

[x] A+4 技能插件协议（SKILL.md + triggers + 懒加载）与工具插件目录对齐
- 目标文件：`quentin/skills/manager.py`（或新增 `quentin/skills/plugin_loader.py`）

[x] A+5 可执行技能插件（manifest.yaml + logic.py）与 Planner 可见性
- 目标文件：
  - `quentin/skills/exec_plugin_loader.py`
  - `quentin/skills/manager.py`
  - `quentin/execution/skill_executor.py`
  - `quentin/cognitive/loop_impl.py`
- DoD：
  - 在 `extensions/skills/<id>/` 放入 `manifest.yaml` + `logic.py` 即可被 Executor 执行
  - Planner payload 自动带 `available_exec_skills`
- 测试：
  - `pytest tests/unit/test_exec_skill_plugin.py -q`
  - `pytest tests/unit/test_exec_skill_plugins_listing.py -q`

## B. P1 技能协议与隔离执行

[x] B1 定义 SKILL.md 元数据协议
- 目标文件：
  - 新增 `quentin/skills/skill_markdown.py`
  - 文档更新 `docs/improve/`
- 任务：
  - frontmatter 字段：`name`、`description`、`requires`、`triggers`
  - 解析器：提取元数据和正文
- DoD：
  - 能稳定解析合法 SKILL.md
  - 非法 frontmatter 返回可诊断错误
- 测试：
  - 新增 `tests/unit/test_skill_markdown_parser.py`
- 预计：0.5d

[x] B2 在 SkillManager 增加懒加载能力
- 目标文件：`quentin/skills/manager.py`
- 任务：
  - 新增 `list_markdown_skills()`、`load_markdown_skill(skill_id)`
  - 增加触发匹配函数（基于 description/triggers）
- DoD：
  - 不全量读取所有 SKILL.md
  - 命中后按需加载正文
- 测试：
  - 新增 `tests/unit/test_skill_manager_markdown_lazyload.py`
- 预计：1d

[x] B3 保持 JSON registry 与 Markdown 双轨一致性
- 目标文件：
  - `quentin/skills/registry.py`
  - `quentin/skills/store.py`
- 任务：
  - 约定 skill_id 映射关系
  - registry 作为状态/统计源，SKILL.md 作为 SOP 源
- DoD：
  - 同一 skill 可同时被 registry 查到、被 markdown 加载
- 测试：
  - 新增 `tests/integration/test_skill_registry_markdown_bridge.py`
  - `pytest tests/integration/test_skill_registry_markdown_bridge.py -q`
- 预计：0.5d

[x] B4 自编程引入临时工作区隔离
- 目标文件：
  - `meta_agent/self_programming/engine_v2.py`
  - `meta_agent/self_programming/test_runner.py`
  - `meta_agent/self_programming/infra/git_ops.py`
- 任务：
  - 增加 `QUENTIN_SELFPROG_ISOLATED_WORKDIR` flag
  - 默认在 `mktemp -d` 目录执行自编程任务
  - 仅回传 patch/report，不直接污染主仓库
- DoD：
  - 任务失败不影响主仓库工作树
  - 任务成功可回放 patch
- 测试：
  - `pytest tests/integration/test_run_self_programming_cycle_v2_smoke.py -q`
  - 新增 `tests/integration/test_selfprog_isolated_workdir.py`
- 预计：1.5d

## C. P2 受控 PTY 与后台编排

[x] C1 新增受控交互式 Shell 会话能力
- 目标文件：
  - 新增 `quentin/tools/interactive_shell.py`
  - 注册到 `quentin/tools/manager.py`
- 任务：
  - API：start/write/poll/log/kill
  - 安全：白名单命令 + 时长限制 + 环境限制
- DoD：
  - 能处理 y/n 与验证码类交互
  - 审计日志完整
- 测试：
  - 新增 `tests/unit/test_interactive_shell.py`
- 预计：1.5d

[x] C2 后台任务统一协议
- 目标文件：
  - `quentin/runtime/system_events.py`
  - `meta_agent/api/server.py`
  - 相关 CLI/daemon 调度代码
- 任务：
  - 定义 background task 事件结构
  - 标准化完成、失败、取消、超时事件
- DoD：
  - 前端/API 可消费统一结构
- 测试：
  - 新增 `tests/integration/test_background_task_events.py`
- 预计：1d

## D. 配置与开关

[x] D1 新增 feature flags（默认安全关闭）
- `QUENTIN_EXTERNAL_CONTENT_SHIELD=true`
- `QUENTIN_SKILL_MD_ENABLED=false`
- `QUENTIN_SELFPROG_ISOLATED_WORKDIR=false`
- `QUENTIN_INTERACTIVE_SHELL_ENABLED=false`
- `QUENTIN_WAKE_ENABLED=true`

[x] D2 文档与运维说明同步
- 更新：
  - `README.md`（开发说明）
  - `docs/SELF_PROGRAMMING.md`（自编程隔离模式）
  - `docs/improve/`（迁移记录）

## E. 验收清单（发布前）

[x] E1 单测通过
- `pytest tests/unit -q`

[x] E2 关键集成通过
- `pytest tests/integration/test_task_source_obs.py -q`
- `pytest tests/integration/test_run_self_programming_cycle_v2_smoke.py -q`

[x] E3 手工回归
- 并发同 session 请求，确认 lane 串行
- Web 外部内容注入样本，确认 shielding 生效
- 后台任务完成后 `qctl wake` 能推送事件

[x] E4 回滚验证
- 逐项关闭 flags，确认系统恢复到原行为

## F. 执行顺序（建议）

1. A1 -> A2 -> A4  
2. A3  
3. B1 -> B2 -> B3  
4. B4  
5. C1 -> C2  
6. D/E 全量验收
