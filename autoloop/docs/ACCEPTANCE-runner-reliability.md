# Acceptance Checklist · Runner Reliability

- [ ] Codex runner 在 state_db 异常时可自动降级，不再卡死在单一模式。
- [ ] 单次 codex 执行超时受 `codex_attempt_timeout_seconds` 硬限制。
- [ ] 任何超时执行会清理进程组，不残留长期子进程。
- [ ] `contract_validator` 对 `state_db_falling_back` 做失败判定。
- [ ] `runtime/metrics/runner_health.json` 输出以下字段：
  - `state_db_fallback_count`
  - `session_degraded_count`
  - `execution_timeout_count`
  - `probe_failure_count`
- [ ] `python -m app.main system-metrics-report` 的输出包含 `runner_health`。
- [ ] `./scripts/ci_gate.sh` 全绿。
