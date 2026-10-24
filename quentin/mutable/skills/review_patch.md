Input:
- Patch diff or changed files
- Task objective and constraints

Goal:
- Perform a focused code review for correctness, safety, and regressions.

Steps:
1. Verify patch matches the stated objective.
2. Check for behavioral regressions and edge-case gaps.
3. Validate tests are meaningful and cover changed paths.
4. Assess risk level and recommend next action.

Output:
- `review_verdict`: approve | revise
- `findings`: concrete issues with file references
- `test_gaps`: missing tests or weak assertions
- `risk_level`: low | medium | high

Guardrails:
- Do not merge or apply changes directly.
- Be specific; avoid generic comments.
- Prioritize correctness and safety over style.

