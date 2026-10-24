# Quentin Runtime Intelligence Upgrade Plan (v1)

Date: 2026-02-10  
Owner: Quentin core loop / planner / executor / councils

## Goals
- Eliminate guess-driven execution for file/system operations.
- Upgrade council outputs from formality to evidence-based critique.
- Prevent strategy collapse after first failed attempt.
- Close the feedback loop from guard/tool failures back into planning.

## Symptom -> Fix Mapping
1. Guessing trap (no environment probing)
- Prompt rule: risky actions require discovery precheck.
- Planner repair: inject discovery step before risky steps.
- Fallback repair: replace single-step fallback with 3-step decomposition.

2. Semantic stagnation (done council says "no reasoning")
- DoneCouncil quality gate for non-done verdicts.
- Auto retry with strict reasoning requirement.
- Deterministic evidence fallback reason when council remains weak.

3. Strategic regression (multi-step -> single-step fallback)
- Reuse prior decomposition when next attempt degenerates.
- Planner repair metadata (`planner_repairs`) for observability.

4. Lack of self-awareness (repeat blocked tools)
- Extract recent denied/error commands from `data/audit_events.jsonl`.
- Inject forbidden action list into planner and executor prompts.
- Keep anti-pattern recovery plan as hard override path.

## Module Changes
- `quentin/cognitive/loop_impl.py`
  - Add forbidden-action extraction from audit events.
  - Inject forbidden actions + previous plan into planner context.
  - Replace single-step fallback with decomposed fallback.
  - Add plan quality repair pass (discovery gate + anti-regression).
  - Strengthen planner hints/prompt constraints.
- `quentin/execution/skill_executor.py`
  - Inject forbidden-actions hint into execution system prompt.
- `quentin/council/done.py`
  - Add council-quality guard, strict retry, and deterministic fallback reason.
- `quentin/goals/done_definition.py`
  - Use council-provided confidence when available.

## Validation
- Unit tests for:
  - Planner hints include forbidden actions.
  - Plan repair injects discovery precheck.
  - Plan repair prevents single-step regression.
  - Executor prompt carries forbidden-action feedback.
  - DoneCouncil retries and fallback reasoning path.
- Keep existing cognitive-loop and executor style tests green.

## Rollout
1. Land code + tests in sandbox runtime.
2. Observe trace signals:
   - `planner_repairs` presence/rate.
   - Drop in `interactive_editor_command` anti-pattern.
   - Reduction in `planner_fallback_single_step`.
3. If stable, tighten by enabling strict done-council mode:
   - `QUENTIN_DONE_COUNCIL_STRICT_REASONING=1` (optional hard mode).
