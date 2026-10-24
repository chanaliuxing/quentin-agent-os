# P9 Red-Blue Exercise Runbook

## Frequency
Quarterly or after major architecture changes.

## Red Team Goal
Bypass the `SafetyKernel` or `ConstraintVerifier` using:
- Prompt injection.
- Obfuscated tool calls.
- Circular dependency attacks.

## Blue Team Goal
Detect and suppress attacks with minimal latency.

## Output
Run `scripts/run_red_blue_exercise.py` to generate the exercise scorecard.
