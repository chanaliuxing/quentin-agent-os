Input:
- Goal text
- Target file(s)
- Relevant failing test or error output

Goal:
- Produce a safe, minimal patch that resolves the issue.

Steps:
1. Read target file(s) and verify current behavior.
2. Make the smallest change that addresses root cause.
3. Add or update tests to cover the fix.
4. Re-run targeted checks and summarize risk.

Output:
- `patch_summary`: what changed and why
- `files_changed`: list of paths
- `test_plan`: commands and expected result
- `risk_notes`: potential regressions and mitigations

Guardrails:
- Do not introduce unrelated refactors.
- Prefer deterministic edits over broad rewrites.
- Keep public behavior stable unless explicitly requested.

