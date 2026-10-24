# Event Protocol & Channel Gateway TODO (Post-Benchmark)

## 基准结论（本轮）
- 工具适配基准已运行：`PYTHONPATH=. python scripts/tool_adaptation_benchmark.py --ci-mode --soft-timeouts`
- 当前得分：`quality_score=1.0`，但该基准对事件流与网关产品化覆盖不足，存在“满分但盲区”。
- 运行日志暴露的真实风险信号：
  - `listener discord start failed: 429 too many requests`
  - `fatal: not a git repository`
  - 说明外部通道、运行环境依赖在真实场景仍有脆弱点。

## 与顶级产品模块差距（客观）

### 1) 事件协议层
- 现状：已具备 `BrainEvent`、`subscribe_session`、`drain_events`、turn/tool/compaction/message 关键事件。
- 差距：
  - 缺少协议版本协商与向后兼容策略（只做了 `__brain_event_v1`，未有协商机制）。
  - 缺少事件幂等键、重放游标（cursor）与 at-least-once/at-most-once 可选语义。
  - 缺少跨进程消费者的标准 ACK/重试协议。

### 2) Channel Gateway 产品化
- 现状：有 `environment_bus` 与 UI broadcaster，但与统一事件协议尚未完全收敛。
- 差距：
  - 缺少统一网关接口（SSE/WS/HTTP pull）与会话鉴权、速率限制、租户隔离。
  - 缺少通道级 SLA 指标（订阅延迟、断流恢复时延、丢包率）。
  - 缺少对 OpenClaw `subscribeEmbeddedPiSession` 对齐的端到端契约测试。

### 3) Benchmark 可信度
- 现状：工具适配场景覆盖较好，但事件网关覆盖弱。
- 差距：
  - 缺少“事件序列可重建 UI/日志”的自动评分项。
  - 缺少“订阅者异常风暴”与“网关限流/429”压力场景。
  - 缺少多会话并发下顺序一致性（per-session seq 单调）验证。

## 落地 TODO（按优先级）

## P0（本周必须）
- [x] 增加 `BrainEvent` 游标字段（`cursor`/`offset`）与 `drain_events(after_cursor=...)`。
- [x] 增加 `subscribe_session` 的异常计数与熔断统计，输出诊断事件（而非仅吞异常）。
- [x] 新增 `event_protocol_benchmark.py`：强制校验一轮 turn 的事件可重建日志（顺序、完整性、无断流）。
- [x] 增加并发测试：100+ 会话并发 tool 事件，验证每会话 `seq` 单调递增。

## P1（两周内）
- [x] 把 `environment_bus`/`UI broadcaster` 映射为 `BrainEvent` 统一出口（单协议多通道）。
- [x] 新增 gateway 层 API：`/brain-events/stream`（SSE）与 `/brain-events/drain`（cursor pull）。
- [x] 增加通道治理（基础版）：鉴权（API key）、rate-limit。
- [x] 增加通道治理（增强版）：租户隔离、backpressure。
- [x] 补充 replay 语义测试：断线续传、重复投递去重、跨进程重启恢复。

## P2（产品化完善）
- [x] 事件 schema registry（版本迁移策略 + 兼容矩阵）。
- [x] 增加通道生态适配器（Discord/Slack/Webhook）并统一 gateway contract。
- [x] 将 benchmark 评分拆为“能力分 + 可靠性分 + 运营分”，避免单一总分掩盖风险。

## 验收门槛（下一轮）
- [x] 单轮 turn 能 100% 重建 UI 时间线（turn/tool/compaction/message）。
- [x] 订阅回调 10% 故障注入下，主流不丢、不断、可回放。
- [x] 429/限流场景自动降级并可观测（告警 + 事件自描述）。
- [x] Channel gateway 基准至少 20 个失败注入 case，分项得分均 ≥ 0.85。
