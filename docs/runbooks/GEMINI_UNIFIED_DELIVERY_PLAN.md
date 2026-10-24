# Gemini 统一落地清单（合并版）

本文件合并以下两件事，按一个流水线一次性落地：
- `verify_system` 稳定化与验收（执行计划 + UAT）
- 大脑“变聪明”工程化改造（质量门禁/幂等/分层决策/鲁棒解析/反模式记忆）

---

## A. 工作包 1：`verify_system` 稳定化（必须先做）

### A1. 核心目标
1. 修复格式脆弱导致的假失败。
2. 解决语义重复执行（幂等）。
3. 给简单任务降决策开销（fast path）。
4. 强制计划执行对齐（先观察再修改）。

### A2. 落地顺序
1. Executor 增加 JSON salvage + `format_soft_fail` 分类。  
2. 增加 `goal_fingerprint` + 文件状态哈希幂等门。  
3. 增加 `council_fast_path`（simple task 单成员/轻判定）。  
4. 增加 step contract（mutate 前必须有 observe 证据）。  
5. 日志补齐：`format_salvaged/idempotent_hit/fast_path_used/goal_fingerprint`。

### A3. 必做测试
- 单测：
  - `tests/unit/test_executor_json_salvage.py`
  - `tests/unit/test_executor_failover_metrics.py`
  - `tests/unit/test_goal_fingerprint_idempotency.py`
  - `tests/unit/test_council_fast_path_routing.py`
  - `tests/unit/test_step_contract_guard.py`
- 集成：
  - `tests/integration/test_verify_system_idempotent_rerun.py`
  - `tests/integration/test_verify_system_fast_path_latency.py`
  - `tests/integration/test_verify_system_format_robustness.py`
  - `tests/integration/test_verify_system_plan_execute_alignment.py`

### A4. 验收 Gate
- 连续 3 次 `verify_system.py` 成功率 100%。
- 二次同任务不重复写关键文件（或仅差异写）。
- simple task P50 < 30s，P95 < 60s。
- `format` 不再导致 `done=false`。

---

## B. 工作包 2：大脑“变聪明”工程化（在 A 完成后做）

### B1. 核心目标
1. 写完必查（静态检查门禁）。  
2. 没测没完（done 依赖测试通过证据）。  
3. 先看再做（语义预感知 + 幂等短路）。  
4. 大事开会小事快跑（快慢路径分层）。  
5. 解析鲁棒（本地模型输出清洗）。  
6. 反模式可学习（失败经验注入下一轮）。

### B2. 落地顺序
1. `post_write_quality_gate`：`ruff check`（可选 `mypy`）。  
2. planner 强制插入 `s_test`，done 必须看到 pytest green 证据。  
3. `semantic_pre_sensing`：目标已满足则 `already_done`/增量修复。  
4. 复杂度分层：`fast_path` vs `council_path`。  
5. `output_sanitizer` + `format_salvaged` 标记。  
6. 反模式记忆写入 STS，并自动注入下轮提示。

### B3. 必做测试
- 单测：
  - `tests/unit/test_quality_gate_static_check.py`
  - `tests/unit/test_planner_mandatory_test_step.py`
  - `tests/unit/test_done_requires_test_evidence.py`
  - `tests/unit/test_semantic_pre_sensing_idempotent.py`
  - `tests/unit/test_fast_path_routing.py`
  - `tests/unit/test_output_sanitizer_local_llm.py`
  - `tests/unit/test_antipattern_memory_injection.py`
- 集成：
  - `tests/integration/test_verify_system_with_quality_gate.py`
  - `tests/integration/test_verify_system_mandatory_tests_flow.py`
  - `tests/integration/test_verify_system_rerun_idempotent.py`
  - `tests/integration/test_verify_system_fast_path_latency.py`
  - `tests/integration/test_verify_system_format_resilience.py`

### B4. 验收 Gate
- 注入 `NameError` 必须在 done 前被拦截。  
- 无测试通过证据不得 done。  
- `idempotent_hit=true` 可观测。  
- `self_awareness_failover_reason=format` 可出现但不能阻断完成。  

---

## C. 一键验收流水线（Gemini 最终必须跑）
```bash
bash scripts/qa/preflight_verify_system.sh

pytest -q tests/unit/test_executor_json_salvage.py \
  tests/unit/test_executor_failover_metrics.py \
  tests/unit/test_goal_fingerprint_idempotency.py \
  tests/unit/test_council_fast_path_routing.py \
  tests/unit/test_step_contract_guard.py \
  tests/unit/test_quality_gate_static_check.py \
  tests/unit/test_planner_mandatory_test_step.py \
  tests/unit/test_done_requires_test_evidence.py \
  tests/unit/test_semantic_pre_sensing_idempotent.py \
  tests/unit/test_fast_path_routing.py \
  tests/unit/test_output_sanitizer_local_llm.py \
  tests/unit/test_antipattern_memory_injection.py

pytest -q tests/integration/test_verify_system_idempotent_rerun.py \
  tests/integration/test_verify_system_fast_path_latency.py \
  tests/integration/test_verify_system_format_robustness.py \
  tests/integration/test_verify_system_plan_execute_alignment.py \
  tests/integration/test_verify_system_with_quality_gate.py \
  tests/integration/test_verify_system_mandatory_tests_flow.py \
  tests/integration/test_verify_system_rerun_idempotent.py \
  tests/integration/test_verify_system_fast_path_latency.py \
  tests/integration/test_verify_system_format_resilience.py

python3 verify_system.py
python3 verify_system.py
```

---

## D. 交付物（Gemini 提交时必须附带）
1. 变更文件清单 + 关键设计说明。  
2. 全部测试结果摘要（unit/integration）。  
3. 三段证据日志：
   - 质量门禁拦截错误；
   - 幂等命中跳过重复写；
   - 格式清洗成功且最终 done。  
4. Gate 逐项 PASS/FAIL 表。  

---

## E. 问题证据映射（必须逐条回归）
- `is_done=true` 但被判未完成（旧逻辑兼容问题）：
  - `data/traces/events.jsonl:165`
- 语义去重失效（重复写同文件）：
  - `data/audit_events.jsonl:248`
  - `data/audit_events.jsonl:251`
  - `data/audit_events.jsonl:266`
  - `data/audit_events.jsonl:269`
- 决策开销过重（planner/done council）：
  - `data/llm_raw_history.jsonl` 中 `council_member:planner:*`
  - `data/llm_raw_history.jsonl` 中 `council_arbiter:planner`
  - `data/llm_raw_history.jsonl` 中 `council_member:done:*`
- 计划-执行脱节（先检查后写未被遵守）：
  - 计划：`data/traces/events.jsonl:227`
  - 执行：`data/traces/events.jsonl:259`
- 历史额外问题（已修/需回归）：
  - 双后缀 URL：`data/traces/events.jsonl:14`
  - 旧轮次超时：`data/llm_raw_history.jsonl:205`, `data/llm_raw_history.jsonl:133`

## F. 优先级改造项（与上面证据一一对应）
1. Executor 增加宽松 JSON 提取/修复，并将 `format` 从硬失败率降权。  
2. 增加语义幂等门：`goal_fingerprint + 文件状态哈希`，命中即 `skip/verify`。  
3. council 增加 fast-path：简单文件任务单成员或跳过 arbiter。  
4. 强制 plan step contract：先观察后修改，违约打回当前 step。  
