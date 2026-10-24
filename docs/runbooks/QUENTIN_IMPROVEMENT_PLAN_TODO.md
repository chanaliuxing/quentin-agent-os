# Quentin 核心工程加固计划（Linting / Testing / Sensing / Efficiency）

## 目标
- 把系统从“能做完”升级到“稳定做对、可重复、可审计”。
- 重点解决四类问题：
  1) 写完必查（Linting）  
  2) 没测没完（Testing）  
  3) 先看再动（Sensing）  
  4) 大事开会，小事自决（Efficiency）  

## 范围与边界
- 范围：`quentin/` 主执行链路（CognitiveLoop + Executor + Council + Tools + Self-awareness）。
- 边界：不追求一次性重构全架构；优先“硬门禁 + 可观测 + 渐进式启用（feature flags）”。

## 现状关键缺口（客观）
- **Linting**：`fs.write_file` 仅 `compile()` 语法检查，抓不住未导入/未定义名等（语义级错误）。缺少任务级、可配置的 lint gate。
- **Testing**：pytest 存在但不是 Done 的硬门槛；缺“必须有测试 + 必须看到通过证据”的协议化证据链。
- **Sensing**：存在幂等/step contract 的实现碎片，但未统一接入主执行器（`skill_executor` 为主链路）。
- **Efficiency**：Council 有 fast-track，但复杂度判定偏粗糙；简单任务仍可能走重路径，造成时间/成本浪费。

---

## 改进计划（分阶段，建议逐步开关）

### Phase 0：基线与可观测（1 天）
目标：先能量化“变好没变好”。
- 统一写入以下字段到 trace/audit：
  - `goal_fingerprint`、`idempotent_hit`、`fast_path_used`、`format_salvaged`
  - `quality_gate_passed`、`tests_passed`（结构化字段，非自然语言）
- 建立基线报表脚本（最少输出 P50/P95 latency、失败原因分布、重复写次数）。

### Phase 1：写完必查（Linting Gate）（1–2 天）
目标：写完代码后，**在同一轮**发现并修复低级错误；否则禁止 Done。
- 在项目中正式引入并固定工具链（推荐）：
  - `ruff`（必选），`mypy`（可选）
- 实现任务级 quality gate（不是工具级）：
  - 只对本轮变更文件运行：`ruff check <files>`（可选 `ruff format --check`）
  - 失败 => 立刻进入修复循环；done_check 不允许通过
- 失败归因要精细化：
  - `lint_failed`、`typecheck_failed`、`import_error`（别都归为 format）

### Phase 2：没测没完（Testing Gate）（2–3 天）
目标：代码任务必须产出可持续运行的测试，且 Done 必须看到 green 证据。
- Planner 强制插入 `s_test`：
  - 判定“代码类任务”（触碰 `.py`、新增模块、改接口、改插件逻辑等）=> 计划中必须出现测试步骤
- Executor 采集并结构化记录 pytest 结果：
  - returncode、failed_count、duration、关键失败片段（截断）
- DoneCouncil 增加硬门槛：
  - 未看到 `tests_passed=true`（结构化）=> 禁止 done

### Phase 3：先看再动（Sensing + 幂等 + step contract）（2–4 天）
目标：避免重复劳动；强制“观察→修改→验证”的安全序列。
- 统一接入幂等门到**主执行链路**：
  - 目前幂等/契约实现不应只存在于另一套 Executor；需要在 `skill_executor` 的写入/替换路径生效
- 增加 `semantic_pre_sensing` 算子（执行前）：
  - 对目标产物（文件/目录/命令验证）做最小探测
  - 若已满足语义 => `already_done` / `verify_only`
- step contract：
  - step.kind = `observe | mutate | verify`
  - mutate 前必须存在 observe 证据（trace 可检索），否则拒绝执行并要求重规划

### Phase 4：大事开会，小事自决（Efficiency）（2–4 天）
目标：简单维护任务从“分钟级”降到“秒级/十秒级”，复杂任务保持安全。
- 引入工程化复杂度分级器（不要只靠 prompt 关键词）：
  - 维度：触碰文件数、风险等级、是否需要测试/迁移、是否外部依赖、是否跨模块
- fast-path 策略（建议默认开给 maintenance/low risk）：
  - planner：单成员
  - done：单成员或规则化判定（依赖结构化证据：lint/test/verify）
  - 跳过 arbiter（或只在 disagree 时启用）
- 对本地慢模型的超时策略：
  - “有进展就等”：需要协议层能观察到进度/心跳（否则只能放宽 timeout）

---

## TODO List（落地清单）

### 0) 基线与报表
- [ ] 增加 `scripts/qa/report_execution_health.py`：输出 P50/P95、失败原因、重复写次数、council 耗时分布
- [ ] 在 trace/audit 中统一字段：`goal_fingerprint/idempotent_hit/fast_path_used/format_salvaged`

### 1) Linting Gate
- [ ] `pyproject.toml` 增加 `ruff`（以及可选 `mypy`）依赖与配置
- [ ] 实现 `code.verify`（或等价）工具：支持 `ruff check` +（可选）`mypy`
- [ ] Executor 在写文件/应用 patch 后自动调用 quality gate（只检查变更文件）
- [ ] Self-awareness 增加 `lint_failed` 归因与建议动作

### 2) Testing Gate
- [ ] Planner 强制插入 `s_test`（代码类任务）
- [ ] Executor 增加 pytest runner（结构化输出：`tests_passed/failed_count/duration`）
- [ ] DoneCouncil：若 `tests_passed != true` 则禁止 done
- [ ] 为插件/工具类任务提供默认测试模板（最小三场景：success/missing arg/command error）

### 3) Sensing / 幂等 / Step contract
- [ ] 在主执行器（`skill_executor`）中接入 `IdempotencyGate`（写/替换前判断）
- [ ] 新增 `goal_fingerprint` 生成与持久化（任务文本归一化 + 目标产物 + 约束）
- [ ] 增加 `semantic_pre_sensing`：运行前读关键文件、检查目录、健康检查命令
- [ ] step.kind & contract enforcement：mutate 前必须 observe

### 4) Efficiency（Fast/Slow Path）
- [ ] 实现复杂度分级器（文件数/风险/外部依赖/测试需求）
- [ ] council fast-path：simple task 单成员 + 跳过 arbiter（必要时才启用）
- [ ] 为 local/remote 模型设置不同 timeout/重试策略（并写入可观测字段）

### 5) 测试补齐（必须覆盖核心门禁）
- [ ] 单测：quality gate 拦截未导入/NameError
- [ ] 单测：planner 必含 `s_test`
- [ ] 单测：done 必须看到 `tests_passed=true`
- [ ] 单测：幂等命中不触发重复写
- [ ] 集成：同任务连跑 2 次，第二次不重写且仍 verify 通过
- [ ] 集成：fast-path 延迟显著下降且不牺牲正确性

---

## 验收标准（Definition of Done）
- **正确性**：核心任务完成（产物存在且可验证）。
- **质量门禁生效**：
  - 注入明显 lint 错误 => 必须被拦截，且不可 Done。
  - 缺少测试通过证据 => 不可 Done。
- **幂等**：同任务重复运行第二次不重写关键文件（或仅差异更新一次）。
- **效率**：simple task P50 < 30s，P95 < 60s（以报表脚本输出为准）。
- **可观测**：上述所有门禁/路径选择均能在 `events.jsonl/audit_events.jsonl` 中被检索到。

## 推荐验收命令
```bash
bash scripts/qa/preflight_verify_system.sh
pytest -q
python3 verify_system.py
python3 verify_system.py
python3 scripts/qa/report_execution_health.py --minutes 60
```

