# Execution Gap Todo (Taylor vs OpenClaw)

Last update: 2026-02-21

## Status Summary
- Estimated execution-layer parity: `~100%` (execution todo baseline fully landed).
- Current gap list for this execution-parity track is cleared; remaining work is optional hardening/scale optimization.

## Completed Phases
- [x] P0-1 Cron runner with due-task enqueue path
- [x] P0-2 Listener reliability baseline (dedupe/retry/dead-letter + manager restart/rate-limit)
- [x] P1-3 Node assignment lifecycle (assign/release/reconcile/history/auto-assign)
- [x] P1-4 Web patch expansion and externalized rules module
- [x] P1-5 OCR strategy interface (`auto/tesseract/hint/none/vision_api`)
- [x] P2-6 Canvas lifecycle extension (`transition/ack/list_acks`)
- [x] Daemon integration: idle-loop cron runner tick + assignment reconcile/auto-assign
- [x] P2-7 Communication event semantics in listener (`message/edit/delete/thread_move`)
- [x] P2-8 Stale-node assignment migration in reconcile loop
- [x] P3-9 Adapter reconnect telemetry export into observability overview (`communication` domain)
- [x] P3-10 Communication + canvas handshake surfaced in observability dashboard metrics/summary
- [x] P4-11 Lease renew drift/contention + fencing conflict anomaly detection and remediation
- [x] P4-12 Dead-letter long-window trend anomaly alerts

## Remaining Gaps
1. Platform-depth for external communications
- [x] Discord/Slack event parity for edit/delete/thread-move events
- [x] Production-grade reconnect reason taxonomy + metrics per adapter (manager+session status)
- [x] Platform-specific rate-limit backoff profiles (preset + env override)

2. Distributed execution depth
- [x] Multi-node lease arbitration baseline (`acquire_lease/release_lease/lease_status` with TTL)
- [x] Lease heartbeat renew/jitter and leader election baseline (`renew_lease/elect_leader`)
- [x] Leader election quorum + epoch fencing baseline (`quorum/expected_epoch/fencing_token`)
- [x] Assignment migration policy when node goes stale mid-task
- [x] Cross-process assignment lock strategy for clustered runners (assignment file lock)

3. Web/media quality hardening
- [x] Golden dataset regression for site patch quality (StackOverflow/GitHub/Medium/Dev.to baseline)
- [x] OCR quality score and fallback routing logic (vision_api <-> tesseract baseline)
- [x] Readability extraction diff metrics for noisy pages

4. Canvas runtime protocol hardening
- [x] Ack timeout watcher and retry hint generation
- [x] Component state transition policy checks (invalid edges)
- [x] UI-side handshake status mirrored into runtime health panel (`session.status`)

## Next Recommended Sprint (Optional)
1. Add lease event retention/compaction policy for very long-running clusters.
2. Add dashboard sparklines for dead-letter and fencing trend windows.
3. Add canary chaos scenarios for leader churn under partial network partition.
