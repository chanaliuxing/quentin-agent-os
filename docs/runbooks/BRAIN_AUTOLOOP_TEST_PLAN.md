# Brain AutoLoop 测试方案与验收标准

## 1) 目标与范围
- 验证 `scripts/brain_autoloop.py` 的主闭环是否可靠：`verify -> analyze -> fix -> apply -> test -> (benchmark)`.
- 验证“停止条件”是否生效，尤其是：
  - Gemini 配额/Token 用尽立即停机。
  - Fixer 非 JSON / 无实际改动时停机。
  - 可选 benchmark 回归拦截。

## 2) 测试前准备
- 复制配置：
  - `cp config/brain_autoloop.example.json config/brain_autoloop.local.json`
- 建议将 `max_iterations` 设为 `2~3`，避免长跑。
- 所有测试产物检查目录：`generated/brain_autoloop/<timestamp>/`.

## 3) 测试矩阵（给 Gemini 执行）

### T1 基线冒烟（流程可跑通）
- 配置：
  - `analyzer_command: "gemini -p {prompt}"`
  - `fixer_command: "gemini -p {prompt}"`
  - `require_benchmark_improve: false`
- 执行：
  - `python3 scripts/brain_autoloop.py --config config/brain_autoloop.local.json --max-iterations 1`
- 预期：
  - 生成 `iter_001` 目录与 `run_report.json`。
  - 至少包含：`verify_*`, `analyzer_*`, `fixer_*`, `apply_report.json`, `tests_*`。

### T2 Token/Quota 用尽立即停机（Analyzer）
- 配置（临时）：
  - `analyzer_command: "python3 -c \"print('Error 429 quota exceeded')\""`
- 执行同 T1。
- 预期：
  - `run_report.json.stop_reason == "gemini_token_exhausted_in_analyzer"`。
  - 不进入 fixer/apply/test 阶段。

### T3 Fixer 非 JSON 合约停机
- 配置（临时）：
  - `analyzer_command: "python3 -c \"print('{\\\"summary\\\":\\\"ok\\\",\\\"issues\\\":[]}')\""`
  - `fixer_command: "python3 -c \"print('not json')\""`
- 预期：
  - `stop_reason == "fixer_invalid_json_contract"`。
  - 生成 `fixer_raw.txt`，但无有效 `changes` 落地。

### T4 Fixer JSON 但无改动停机
- 配置（临时）：
  - `fixer_command: "python3 -c \"print('{\\\"summary\\\":\\\"noop\\\",\\\"changes\\\":[],\\\"tests\\\":[],\\\"notes\\\":\\\"none\\\"}')\""`
  - `require_file_changes: true`
  - `stop_on_no_file_change: true`
- 预期：
  - `stop_reason == "no_file_changes_applied"`。
  - `apply_report.json.changed_files` 为空。

### T5 Fixer 有效改动并被落地
- 配置（临时）：
  - `fixer_command` 输出合法 JSON，包含 1 条 write 改动到允许路径，如 `generated/autoloop_smoke.txt`。
- 预期：
  - `apply_report.json.changed_files` 包含该文件。
  - 文件真实存在且内容匹配。

### T6 写路径越权拦截
- 配置（临时）：
  - Fixer 输出写入 `outside/evil.txt`。
- 预期：
  - `apply_report.json.errors` 包含 `path blocked by allowlist`。
  - 无越权文件写入。

### T7 Benchmark 对比与回归拦截
- 前置：
  - 先运行一次 benchmark 生成 `generated/benchmarks/web_search_benchmark_prev.json`。
- 配置：
  - `benchmark_command` 使用 `scripts/benchmark_websearch_tool.py`。
  - `require_benchmark_improve: true`
- 预期：
  - 若分数未提升，`stop_reason == "benchmark_not_improved"`。
  - 若分数提升，继续下一轮或按其他条件结束。

## 4) 验收标准（必须同时满足）
- A1. 可靠性：T1~T6 全部通过，且每个停止原因与预期一致。
- A2. 安全性：越权写入在 T6 被拦截，仓库外与非 allowlist 路径零落地。
- A3. 可观测性：每轮都产出完整证据文件（prompt/raw/apply/tests/report）。
- A4. 可判定完成：Fixer 必须“进程结束 + JSON 合约有效 + 文件真实变更”才算成功。
- A5. 回归控制：开启 `require_benchmark_improve` 时，分数不提升不得继续“成功推进”。

## 5) 交付物检查清单
- `generated/brain_autoloop/<run>/run_report.json`
- `generated/brain_autoloop/<run>/iter_xxx/apply_report.json`
- `generated/brain_autoloop/<run>/iter_xxx/fixer_plan.json`
- `generated/benchmarks/web_search_benchmark_report.json`

## 6) 建议执行顺序
- 先跑 T2/T3/T4（快速失败路径）-> 再跑 T5/T6（安全与落地）-> 最后跑 T1/T7（闭环与质量门禁）。
