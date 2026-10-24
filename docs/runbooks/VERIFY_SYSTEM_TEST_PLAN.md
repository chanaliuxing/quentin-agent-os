# Verify System 测试计划（给 Gemini 写测试脚本用）

## 1. 目标与范围
- 目标：让 `python3 verify_system.py` 在下次运行时可预测、可观测、可定位失败原因。
- 覆盖范围：配置预检、单元测试、组件测试、离线集成测试、本地 Ollama 集成测试、端到端烟雾测试。
- 本计划重点覆盖本次修复点：
  - `DoneCouncil` 对 `verdict/is_done/done` 的兼容解析。
  - Council 本地模型超时策略（本地宽松、远端严格）。
  - `LLM_BASE_URL` 规范化，防止 `.../api/generate/api/generate`。
  - LLM Raw 日志可观测性与体积控制。

## 2. 进入条件（不满足直接失败）
1. 激活环境：`source venv/bin/activate`
2. 关键变量正确（以 `.env.local` 覆盖最终值）：
   - `LLM_PROVIDER=ollama`
   - `LLM_BASE_URL=http://localhost:11434`
   - `QUENTIN_SQLITE_VEC_PATH=.../sqlite_vec/vec0.dylib`
   - `QUENTIN_COUNCIL_LOCAL_MEMBER_TIMEOUT_S>=420`
   - `QUENTIN_COUNCIL_LOCAL_ARBITER_TIMEOUT_S>=900`
3. 本地 Ollama 可用：`curl -sf http://localhost:11434/api/tags`
4. sqlite-vec 文件存在：`test -f "$QUENTIN_SQLITE_VEC_PATH"`

> Gemini 先实现 `scripts/qa/preflight_verify_system.sh`，把以上 4 条做成硬性 gate。

## 3. 测试分层与用例

## 3.1 L0 预检（必须先跑）
- 脚本：`scripts/qa/preflight_verify_system.sh`
- 输出：`logs/qa/preflight_verify_system.json`
- 检查项：
  - 环境变量读取与生效优先级（`.env` + `.env.local`）。
  - `LLM_BASE_URL` 不能带 `/api/generate` 或 `/api/chat` 后缀。
  - Ollama 连通性 + 目标模型是否在 tags 列表中。
  - sqlite-vec dylib 是否存在且可加载（用最小 Python 片段验证）。

## 3.2 L1 单元测试（快速回归）
- 新增测试文件（Gemini 要写）：
  1. `tests/unit/test_done_council_protocol_compat.py`
     - `final={"is_done": true}` 时 `DoneDecision.is_done=True`
     - `final={"done": "true"}` 时 `DoneDecision.is_done=True`
     - `final={"verdict": "undecided", "is_done": false}` 时为 False
  2. `tests/unit/test_council_timeout_policy.py`
     - route.provider=ollama + localhost => 使用 local floor
     - route.provider=openai + remote url => 使用基础 timeout
  3. `tests/unit/test_model_router_base_url_normalization.py`
     - `http://localhost:11434/api/generate` => 规范化为 `http://localhost:11434`
  4. `tests/unit/test_verify_system_env_contract.py`
     - 验证 `verify_system.py` 的默认 env 不会覆盖已有有效配置
- 命令：
  - `pytest -q tests/unit/test_done_council_protocol_compat.py`
  - `pytest -q tests/unit/test_council_timeout_policy.py`
  - `pytest -q tests/unit/test_model_router_base_url_normalization.py`
  - `pytest -q tests/unit/test_verify_system_env_contract.py`

## 3.3 L2 组件测试（模块协作）
- 新增测试文件：`tests/integration/test_done_council_end_signal_pipeline.py`
- 场景：
  - 构造假 `CouncilManager` 返回 `is_done=true`，验证不会重复 loop。
  - 构造 arbiter timeout，验证 fallback 到 member reply 且流程可继续。
  - 校验 `DoneDecision.raw` 保留原始结构，便于审计。
- 命令：`pytest -q tests/integration/test_done_council_end_signal_pipeline.py`

## 3.4 L3 离线集成测试（CI 友好）
- 环境：
  - `export LLM_STUB=1`
  - `export QUENTIN_MEMORY_STORE=sqlite`
- 用例：
  - 启动最小 cognitive task（不访问真实模型），确保流程闭环。
  - 验证 raw history 仍落盘（即使 stub）。
- 命令：
  - `pytest -q tests/integration/test_bootstrap.py tests/integration/test_executor_protocol_switching.py`

## 3.5 L4 本地 Ollama 集成（真实依赖）
- 环境：
  - `unset LLM_STUB`
  - `LLM_PROVIDER=ollama`
  - `LLM_BASE_URL=http://localhost:11434`
- 用例：
  - `tests/integration/test_ollama_chat_tools_smoke.py`
  - 新增：`tests/integration/test_verify_system_local_ollama_smoke.py`（Gemini 写）
    - 运行一次 `verify_system.py`（总超时 15 分钟）
    - 断言不出现 `api/generate/api/generate`
    - 断言出现 `Memory Store Active` 且任务有最终输出

## 3.6 L5 端到端手工验收
- 命令：
  - `python3 verify_system.py`
- 验收标准：
  - 不出现 404 双后缀 URL 错误。
  - 不出现持续 20 分钟无进展（CPU 近 0 且无新日志）。
  - `data/llm_raw_history.jsonl` 有新增记录，字段完整（`actor/provider/model/ok/latency_ms`）。

## 4. 可观测性与日志验收（必须）
- Gemini 新增脚本：`scripts/qa/check_llm_raw_history.py`
- 检查规则：
  1. 最近 N 分钟每次 LLM 调用都落盘。
  2. `ok=false` 时必须有 `error`；HTTP 错误需带 `error_response_body`（若可读）。
  3. 超大响应走 blob 引用时，`raw_response_ref.path` 文件必须存在。
  4. 统计各 actor 的 P50/P95 latency，并输出 Top 超时来源。
- 产出：`logs/qa/llm_raw_history_report.json`

## 5. 回归执行顺序（固定）
1. `bash scripts/qa/preflight_verify_system.sh`
2. L1 所有单元测试
3. L2 组件测试
4. L3 离线集成
5. L4 本地 Ollama 集成
6. L5 手工 `verify_system.py`

> 任何一步失败，停止后续步骤，先修复再重跑，不允许“带病进入下一层”。

## 6. 给 Gemini 的实现任务清单（可直接复制）
1. 写 `scripts/qa/preflight_verify_system.sh`（严格 `set -euo pipefail`）。
2. 写 `scripts/qa/check_llm_raw_history.py`（支持 `--minutes` 与 `--output`）。
3. 新增 4 个 L1 单测文件（见 3.2）。
4. 新增 1 个 L2 组件测试文件（见 3.3）。
5. 新增 1 个 L4 本地集成测试文件（见 3.5）。
6. 写聚合执行脚本 `scripts/qa/run_verify_system_test_suite.sh`，按第 5 节顺序执行并输出总结。

## 7. 通过门槛（Definition of Done）
- L0~L4 全绿；L5 人工验收通过。
- 不再出现：
  - `http://localhost:11434/api/generate/api/generate`
  - done 判定已完成却继续循环
  - 无 raw 日志导致不可诊断
- 输出物齐全：
  - `logs/qa/preflight_verify_system.json`
  - `logs/qa/llm_raw_history_report.json`
  - `logs/qa/run_verify_system_test_suite.log`

