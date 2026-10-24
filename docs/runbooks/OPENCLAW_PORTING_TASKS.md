# OpenClaw → Quentin Porting Tasks (Mapping + Implementation Checklist)

目标：把 OpenClaw 中已经验证有效的“工程原子件”平移到 Quentin，优先解决近期日志暴露的四类缺陷：
1) parsing fragility（format 虚假失败/报警）  
2) environment blindness（pre-sensing 看不见/误判 not_done）  
3) decision overhead（简单任务也要重 council）  
4) planner–executor 脱节（观察到已存在仍覆盖写入；toolCall/toolResult 不成对）  

本文件给 Gemini 落地用：包含对应关系、任务拆分、具体修改文件、测试清单、以及验收门禁。

相关总体方案参考：`docs/runbooks/BRAIN_HARDENING_PLAN.md`。

---

## 1) 对应关系（OpenClaw → Quentin）

### A. 错误指纹 + 文本清洗（Parsing / Failover）
- OpenClaw
  - `openclaw/openclaw/src/agents/pi-embedded-helpers/errors.ts`
    - `ERROR_PATTERNS`（多级正则指纹）
    - `classifyFailoverReason`
  - `openclaw/openclaw/src/agents/pi-embedded-helpers/errors.ts`（同文件）
    - `sanitizeUserFacingText`（剥离旁白/标签/噪声）
- Quentin（现有）
  - `quentin/llm/failover.py`（基础 error reason 分类，颗粒度较粗）
  - `quentin/council/manager.py`：`_parse_jsonish` / `_fallback_parse`（JSON/YAML 容错）
  - `quentin/llm/tool_call_protocols/json_fallback_protocol.py`：robust JSON parse
- 缺口（要补）
  - 缺少等价 `sanitizeUserFacingText` 的统一清洗器（尤其是剥离多余旁白、避免污染“format”）
  - 缺少更丰富的 pattern 库与“排除项”（OpenClaw 对 image dimension 等误报有排除逻辑）
  - 缺少“format salvage ≠ failure”的指标隔离（健康系统不要被误伤）

### B. Bootstrap Files + Head/Tail 截断（Environment / Sensing）
- OpenClaw
  - `openclaw/openclaw/src/agents/bootstrap-files.ts`（必读文件集合与 session 过滤）
  - `openclaw/openclaw/src/agents/pi-embedded-helpers/bootstrap.ts`（Head 70% + Tail 20% + marker）
- Quentin（现有）
  - `quentin/cognitive/context_snapshots/*`（snapshot 框架）
    - `file_tree.py`（bounded tree，但不是 head/tail，也不具备“必读锚点”策略）
    - `tool_plugins.py`（manifest schema 说明，属于“高密度引导块”雏形）
  - `quentin/cognitive/loop_impl.py`（pre-sensing 已做 focus_paths 聚焦，但仍是 string snapshot）
- 缺口（要补）
  - “锚点文件/目录”的 bootstrap 注入：固定把写策略、manifest、关键 README/AGENTS 等纳入上下文
  - head/tail 截断：避免只看头或只看前 N 行导致误判
  - pre-sensing 从“树字符串”升级为“结构化探测报告”（hash + exists + excerpt）

### C. Lanes + Context Guard（Efficiency）
- OpenClaw
  - `openclaw/openclaw/src/agents/pi-embedded-runner/.../lanes.ts`
  - `openclaw/openclaw/src/agents/context-window-guard.ts`
  - `openclaw/openclaw/src/agents/pi-embedded-runner/compact.ts`
- Quentin（现有）
  - `quentin/infra/concurrency/lanes.py` / `lane_orchestrator.py`（lanes 已有）
  - `quentin/llm/context_budget.py`（context near-overflow 预判 + buffer 已有）
  - `quentin/council/manager.py`（local fast-path 已加）
- 缺口（要补）
  - 用“任务复杂度/风险等级”自动决定是否启用 council，而不是默认重路径
  - 指标化：记录 fast-path 命中率、council 省时比例

### D. Tool Result Guard + Transcript Repair（Planner–Executor 对齐）
- OpenClaw
  - `openclaw/openclaw/src/agents/session-tool-result-guard.ts`（pending tool calls → 补齐 toolResult）
  - `openclaw/openclaw/src/agents/session-transcript-repair.ts`（合成缺失回执）
- Quentin（现有）
  - `quentin/execution/contract.py`：StepContractGuard（先观察后修改）
  - `quentin/execution/idempotency.py` + executor 集成（幂等门）
  - `quentin/llm/tool_call_protocols/*`：工具调用协议适配
- 缺口（要补）
  - 缺少 attempt/session 级 “pending tool result” 守卫（防止 toolCall/toolResult 不成对）
  - 缺少“观察结果驱动的计划剪枝”（即便看到文件存在/一致仍覆盖写入）

---

## 2) 迁移任务拆分（按优先级）

### P0（必须先做）：写操作幂等 + 防退化
1. `fs.write_file`：skip-if-unchanged（文件存在且内容相同 → 不写）
   - 改：`quentin/tools/filesystem.py`
   - 测：新增 `tests/unit/test_fs_write_file_idempotent.py`
2. `manifest.yaml`：fail-closed schema 校验（缺字段不允许写入）
   - 改：`quentin/tools/filesystem.py`（或抽出 `quentin/tools/validators/manifest.py`）
   - 测：新增 `tests/unit/test_manifest_yaml_validation.py`
3. 自动 fingerprint（当 planner 没提供 fingerprint 时，对破坏性写操作自动生成）
   - 改：`quentin/execution/skill_executor.py`（优先）+ 视需要 `quentin/execution/executor.py`
   - 测：新增 `tests/unit/test_executor_autofingerprint_idempotency.py`

**验收**：同一任务跑两次，第二次没有任何真实写入（mtime/hash 不变），step 输出标记 `skipped` 且带 evidence。

### P1：Bootstrap Files + Head/Tail 截断（避免 pre-sensing “视障”）
4. 平移 head/tail 截断算法（OpenClaw `bootstrap.ts`）
   - 新增：`quentin/infra/text/head_tail.py`（或 `quentin/utils/text.py`）
   - 测：`tests/unit/test_head_tail_truncation.py`
5. 实现“Bootstrap Context Files” provider
   - 新增 snapshot provider：`quentin/cognitive/context_snapshots/bootstrap_files.py`
   - 行为：固定注入（可配置）：
     - `AGENTS.md`
     - 写策略（fs write roots / PathGuard）
     - `extensions/tools/**/manifest.yaml`（按任务关键词过滤，默认 top-N）
     - `README.md`（可选）
   - 测：`tests/unit/test_snapshot_bootstrap_files.py`

**验收**：pre-sensing 对 “gemini_cli” 这类任务，注入内容必包含 `extensions/tools/gemini_cli/manifest.yaml`（若存在），且截断同时含 head+tail marker。

### P2：Focused Sensing 报告（结构化，而不是树字符串）
6. 将 pre-sensing 输入改为 “SensingReport JSON”
   - 改：`quentin/cognitive/loop_impl.py`
   - 采集策略：对焦路径 probe：
     - exists（dir/file）
     - sha256(content)
     - excerpt（head/tail）
   - 测：`tests/unit/test_pre_sensing_sensing_report.py`

**验收**：同一项目状态下，pre-sensing 稳定返回 `already_done`，不会被 tree 截断误导。

### P3：Tool Result Guard（补齐缺失回执，强制因果对齐）
7. 在“工具调用 transcript/循环”引入 pending tool results
   - 选择落点（任选其一，推荐 1）：
     1) `quentin/llm/tool_call_protocols/native_tools_protocol.py` + `json_fallback_protocol.py`
     2) `quentin/llm/client.py` 的 `call_llm_with_tools`（如果这里统一构建 tool transcript）
   - 行为：如果模型发出 toolCall，但没有收到 toolResult（或被中断），插入合成 toolResult（error）并强制下一轮处理。
   - 测：`tests/unit/test_tool_result_guard_synthesizes_missing.py`

**验收**：任何一次 attempt，工具调用在 trace 中满足 toolCall/toolResult 成对（允许 synthetic，但必须标记）。

### P4：Error Fingerprinting + sanitizeUserFacingText（format 不再误伤健康）
8. 扩展 `classify_failover_reason`：迁入 OpenClaw ERROR_PATTERNS + 排除项
   - 改：`quentin/llm/failover.py`
   - 测：`tests/unit/test_failover_reason_patterns.py`
9. 新增 `sanitize_user_facing_text` 并在关键链路使用
   - 新增：`quentin/llm/sanitize.py`
   - 用在：
     - council raw 输出（入库前/展示前）
     - self-awareness error_text 抽取前（避免旁白触发“format”）
   - 测：`tests/unit/test_sanitize_user_facing_text.py`
10. SelfAwareness：成功时不设置 `failover_reason=format`（salvage 作为软指标）
   - 改：`quentin/cognitive/self_awareness.py`（只要 overall_success 且无 tool error，就不判 format）
   - 测：`tests/unit/test_self_awareness_format_soft_metric.py`

**验收**：成功执行但存在 JSON salvage 的 attempt，snapshot 为 `healthy`，failure_rate 不被污染；format salvage 计入单独指标。

---

## 3) Gemini 落地清单（可直接照着做）

按顺序执行，任何一步未过测试不进入下一步：

1. 实现 `fs.write_file` 的 skip-if-unchanged + 单测
2. 加 manifest.yaml fail-closed 校验 + 单测
3. executor 自动 fingerprint（mutating step）+ 单测
4. 实现 head/tail 截断工具函数 + 单测
5. 新增 bootstrap snapshot provider（必读锚点文件/目录）+ 单测
6. pre-sensing 改为结构化 SensingReport（hash+excerpt）+ 单测
7. tool result guard（合成缺失 toolResult）+ 单测
8. 扩展 failover patterns + sanitize_user_facing_text + 单测
9. self-awareness “format 软指标”改造 + 单测
10. 集成测试：同一任务跑两次，第二次 0 字节修改、0 schema regression、0 虚假 warning

---

## 4) 验收标准（Release Gate）

### Idempotency / No-Regression
- 同一“创建插件”任务连续跑两次：
  - 第 1 次创建文件齐全（manifest 必含 `entrypoint` 等 required keys）
  - 第 2 次不发生真实写入（hash/mtime 不变），所有写相关 step 为 `skipped`

### Sensing Correctness
- pre-sensing 对焦任务路径输出报告中必须包含：
  - `exists`、`sha256`、`excerpt(head+tail)`、marker

### Tool Causality
- 任意 attempt 中：
  - toolCall 必有 toolResult（允许 synthetic，但必须 `isSynthetic=true`）

### Health Signals
- 成功执行但发生 JSON salvage：
  - `failover_reason` 为空/None
  - salvage 计入单独指标（不进入 failure-rate）

### Performance (Local)
- 简单文件任务默认走 fast-path（单成员、无 arbiter），平均耗时显著低于 baseline（自定义阈值即可）。

---

## 5) 建议的测试命令

- 单元：`pytest -q tests/unit`
- 重点：`pytest -q tests/unit/test_fs_write_file_idempotent.py tests/unit/test_manifest_yaml_validation.py`
- 系统：`python3 verify_system.py`（跑两次，对比第二次无 diff）

