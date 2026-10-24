# Test Plan · Runner Reliability

## Unit
- `pytest tests/unit/test_codex_runner.py -q`
  - 断言 Codex 在 `state_db` 退化信号下自动降级到 `--ephemeral`。
- `pytest tests/unit/test_acceptance_gate.py -q`
  - 断言 log 中出现 `falling_back` 时 `contract_validator=fail`。
- `pytest tests/unit/test_runner_health_metrics.py -q`
  - 断言 runner 健康指标计数可写入和读取。

## Gate
- `./scripts/ci_gate.sh`
  - 回归全量，防止改动破坏既有收敛链路。

## Real Run
- `AGENT_RUNNER_TYPE=codex TEMPORAL_MOCK_MODE=true python -m app.main run ./blueprint.md --mode temporal --profile dev`
- 观察：
  - 是否仍出现挂起；
  - `runtime/metrics/runner_health.json` 指标是否更新；
  - `system-metrics-report` 中 `runner_health` 是否可见；
  - evidence/hook 链路是否完整。
