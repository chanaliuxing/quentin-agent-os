# P7 Audit & Explainability Guide

## Decision Explanations
Every autonomous decision includes an `Explanation` object:
- **Outcome**: What happened.
- **Factors**: Why (scores, weights).
- **Narrative**: Human-readable summary.

## Audit Reports
JSON-structured reports containing:
- Event totals.
- Risk summaries.
- Policy violations.

These reports are immutable artifacts for compliance reviews.
