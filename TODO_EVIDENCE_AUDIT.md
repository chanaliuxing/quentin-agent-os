# Evidence Audit Integration TODOs

- [x] CI/Nightly integration: run P0 audit in CI, fail on errors or implemented→partial/gap regressions; produce audit_report.json (artifact) and optional snapshot/delta in nightly.
- [x] Gate rules: block on implemented status regressions and on any errors; allow warnings.
- [x] Stable outputs: sort details by req_id; order evidence_chain deterministically; sort delta by req_id to avoid noisy diffs.
- [x] Backlog generator: emit backlog.json with top N gap/unknown/partial items including req_id, status, missing_items, module_hint, and rule-based next steps.
- [x] Spec validation: enforce id/title, module_hint must be relative (no '..'); warn when symbols_expected is empty (weak evidence path).
- [x] Tests evidence (P1-A): support tests_expected in spec, add --run-tests flag, score test_pass (+0.5) / test_fail (-0.3); tighten implemented gate to require test or runtime signal.
- [x] Runtime evidence (P1-B): ingest events/run signals (e.g., events.jsonl) and count recent successes as strong evidence (+0.5).
