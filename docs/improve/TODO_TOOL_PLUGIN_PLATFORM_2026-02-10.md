# TODO：工具/技能插件化平台（Quentin）

日期：2026-02-10  
目标：以后“新增工具/技能 = 新增一个目录”，不再修改核心代码（避免全局回归）。

## 目录约定（v1）

插件根目录（可配置）：
- 默认扫描：
  - `extensions/tools/*`
  - `quentin/mutable/extensions/tools/*`
- 覆盖：`QUENTIN_TOOL_PLUGINS_DIRS="extensions/tools,quentin/mutable/extensions/tools"`

单个工具插件目录结构：
- `<plugin_dir>/manifest.yaml`
- `<plugin_dir>/logic.py`
- `<plugin_dir>/README.md`（可选，给人类）
- `<plugin_dir>/SKILL.md`（可选，给模型 SOP，后续接入）

## manifest.yaml（v1）字段

必填：
- `name`: 工具注册名（建议带域前缀，如 `github.stats`）

可选：
- `id`: 插件 id（默认目录名）
- `description`: 工具简介（用于 prompt 工具摘要）
- `entrypoint`: 默认 `logic:run`（v1 仅支持 `logic.py`）
- `domain`: 默认 `core`
- `risk_level`: `low|medium|high|critical`（默认 `medium`）
- `output_trust`: `trusted|untrusted`（默认 `untrusted`）
- `cache.enabled`: true/false
- `cache.ttl_sec`: TTL 秒数

## logic.py（v1）接口

入口函数（默认）：`run(payload: dict, ctx) -> dict | ToolCallResult`

说明：
- `payload`：工具入参
- `ctx`：ToolCallContext（可选）
- 返回值建议 JSON-friendly（dict/list/str/int）

## 已落地（本次）

- 插件发现/注册：`quentin/tools/plugin_loader.py`
- manifest 解析：`quentin/tools/plugin_schema.py`
- sqlite 缓存：`quentin/tools/plugin_cache.py`
- 启动期挂载：`quentin/bootstrap/container.py`
- 单测：`tests/unit/test_tool_plugin_loader.py`

## 下一步（建议）

- [x] 技能插件协议（SKILL.md 懒加载 + triggers）：`quentin/skills/skill_markdown.py` + `quentin/skills/manager.py`
- [x] 单测覆盖：`tests/unit/test_skill_markdown_parser.py` + `tests/unit/test_skill_manager_markdown_lazyload.py`
- [x] 双轨桥接（SKILL.md -> JSON registry）：`SkillManager.bridge_registry_with_markdown()` + `tests/integration/test_skill_registry_markdown_bridge.py`
- [x] `output_trust` 做成 ToolManager after-middleware（统一对所有工具生效）：`quentin/tools/manager.py`
- [x] 可执行技能插件（manifest + logic）v1：`quentin/skills/exec_plugin_loader.py` + `quentin/skills/manager.py` + `quentin/execution/skill_executor.py`
- [x] Planner 可见性：注入 `available_exec_skills`：`quentin/cognitive/loop_impl.py`
- [x] 缓存键声明（key_fields）与大小/逐出策略（含 stale-while-revalidate）
