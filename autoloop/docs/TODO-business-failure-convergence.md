# TODO Business Failure Convergence

- [x] Add formal business failure enums to replace legacy unclassified routing.
- [x] Bind `MISSING_REQUIRED_TEST` to deterministic `replan_from_spec` template.
- [x] Bind `GRADER_FAILED` to deterministic `replan_from_spec` template.
- [x] Bind unmapped business failures to `taxonomy_review_required`.
- [x] Add failure→recovery→terminal mapping contract and unit test coverage.
- [x] Add unclassified business source metrics to hardening report.
- [x] Add rolling-20 monitor and auto taxonomy-ticket creation with dedupe guard.
- [x] Add signature normalization and golden replay pack.
- [x] Add taxonomy promotion report generator.
- [x] Add recovery rollout policy and canary report script.
- [x] Add nightly business-failure batch entry script.
- [ ] Reduce `BUSINESS_REJECTION_UNMAPPED` frequency in real runs (<5% rolling 20 runs).
