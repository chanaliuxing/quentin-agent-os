# Gemini 落地方案：大脑“变聪明”工程计划 + 验收标准

## 0. 背景结论（已确认）
- 功能可达成，但存在工程质量缺口：静态错误漏检、缺测试门槛、重复劳动、简单任务决策过重、格式脆弱导致误判。
- 目标：把系统从“能做完”升级到“可持续稳定做对”。

## 1. 本轮改造目标（必须同时达成）
1. 写完必查：代码实现后强制静态检查。
2. 没测没完：代码类任务必须有测试步骤与通过证据。
3. 先看再做：执行前做语义感知，命中即幂等跳过。
4. 小事快跑：简单任务不走重型 council。
5. 解析鲁棒：本地模型非标准输出不再触发“假失败”。
6. 错误可学习：把失败模式沉淀为下一轮提示约束。

## 2. 分阶段执行（给 Gemini 的实现顺序）

### Phase A：质量硬门禁（静态检查 + 测试门禁）
- 在执行器中新增 `post_write_quality_gate`：
  - 对改动文件运行 `ruff check`（必要时 `mypy` 可选）。
  - 失败时自动触发同轮修复，不允许进入 done_check。
- 在 planner 规则中新增硬约束：
  - 代码实现任务必须自动插入 `s_test` 步骤（编写并运行测试）。
- 在 done 判定增加硬门槛：
  - 未看到 `pytest` 通过证据（日志中 PASS/0 failed）=> 禁止 `is_done=true`。

### Phase B：执行前感知 + 幂等执行
- 在 CognitiveLoop 起点增加 `semantic_pre_sensing`：
  - 解析目标产物（文件/目录/命令验收）并读取当前状态。
  - 若状态已满足目标语义，直接标记 `already_done` 或仅增量修复。
- 增加 `goal_fingerprint`：
  - 由任务文本归一化 + 目标路径 + 约束组成。
  - 与最近成功执行缓存对比，命中时跳过重复写入。

### Phase C：快慢路径决策分层
- 增加复杂度分级器：
  - `fast_path`: 单文件/低风险/无外部依赖 => 单模型执行 + 轻量 done 检查。
  - `council_path`: 多文件/高风险/架构改动 => 完整 council。
- 增加可观测字段：`fast_path_used`, `complexity_tier`。

### Phase D：鲁棒解析层 + 反模式记忆
- Executor 前加 `output_sanitizer`：
  - 去除 markdown fence、前后废话、非 JSON 包裹文本，提取核心 JSON/tool_call。
  - 标记 `format_salvaged=true`。
- 反模式记忆：
  - 当出现 `NameError/import missing/format fail` 时写入 STS。
  - 下一次同类任务自动注入“检查导入/先运行静态检查/固定输出 JSON”提示。

## 3. 代码落点建议
- `quentin/execution/*`: 质量门禁、格式清洗、step gate、测试证据采集。
- `quentin/cognitive/loop_impl.py`: 预感知、goal_fingerprint、幂等短路。
- `quentin/council/manager.py`: fast/council 分层路由。
- `quentin/council/done.py`: done 门槛（必须有测试通过证据）。
- `quentin/memory/*`: 反模式记忆写入与读取注入。

## 4. 测试计划（Gemini 必须补齐）

### 单元测试（必需）
1. `test_quality_gate_static_check.py`
   - 模拟未导入符号，断言 gate 阻断 done。
2. `test_planner_mandatory_test_step.py`
   - 代码任务计划中必须存在 `s_test`。
3. `test_done_requires_test_evidence.py`
   - 无 pytest 通过证据时，done 必须为 false。
4. `test_semantic_pre_sensing_idempotent.py`
   - 目标已满足时不触发写文件。
5. `test_fast_path_routing.py`
   - simple task 命中 fast_path，复杂任务命中 council_path。
6. `test_output_sanitizer_local_llm.py`
   - 垃圾前后缀 + fenced JSON 仍可解析。
7. `test_antipattern_memory_injection.py`
   - 首次失败写 STS，二次任务提示注入成功。

### 集成测试（必需）
1. `test_verify_system_with_quality_gate.py`
   - broken plugin 代码不能通过 done_check。
2. `test_verify_system_mandatory_tests_flow.py`
   - 缺少测试运行日志时不得完成。
3. `test_verify_system_rerun_idempotent.py`
   - 连续两次同任务，第二次无重复写入。
4. `test_verify_system_fast_path_latency.py`
   - 简单任务延迟下降并保留正确性。
5. `test_verify_system_format_resilience.py`
   - 本地模型非标准输出不触发 failover hard-fail。

## 5. 验收标准（UAT Gate）

## Gate-A 正确性
- `verify_system.py` 通过，插件可执行，`gemini --help` 验证成功。
- 插件代码通过 `ruff check`（如启用 mypy 则也通过）。

## Gate-B 质量门禁生效
- 人为注入 `NameError` 时：流程必须在 done 前被拦截。
- 修复后同轮可恢复通过（不需要人工重启全流程）。

## Gate-C 测试驱动生效
- 代码任务必须出现 `s_test`。
- done 判定日志里必须能看到测试通过证据。

## Gate-D 幂等与效率
- 同任务重复运行第二次：`fs.write_file` 次数下降到 0（或仅差异更新）。
- 简单任务 P50 总时延 < 30s；复杂任务仍保持正确性。

## Gate-E 解析与可观测性
- `self_awareness_failover_reason=format` 不再导致 `done=false`。
- 日志可检索字段：`format_salvaged`, `goal_fingerprint`, `idempotent_hit`, `fast_path_used`。

## 6. 标准执行命令（验收流水线）
```bash
bash scripts/qa/preflight_verify_system.sh
pytest -q tests/unit/test_quality_gate_static_check.py \
  tests/unit/test_planner_mandatory_test_step.py \
  tests/unit/test_done_requires_test_evidence.py \
  tests/unit/test_semantic_pre_sensing_idempotent.py \
  tests/unit/test_fast_path_routing.py \
  tests/unit/test_output_sanitizer_local_llm.py \
  tests/unit/test_antipattern_memory_injection.py
pytest -q tests/integration/test_verify_system_with_quality_gate.py \
  tests/integration/test_verify_system_mandatory_tests_flow.py \
  tests/integration/test_verify_system_rerun_idempotent.py \
  tests/integration/test_verify_system_fast_path_latency.py \
  tests/integration/test_verify_system_format_resilience.py
python3 verify_system.py
python3 verify_system.py
```

## 7. Gemini 交付要求（必须）
- 变更清单（模块 + 关键设计说明）。
- 新增测试列表 + 运行结果摘要（通过/失败数）。
- 三段证据日志：
  1) 质量门禁拦截 NameError；
  2) 幂等命中跳过重复写；
  3) format salvage 成功且 done=true。
- Gate-A~E 逐项 PASS/FAIL。

