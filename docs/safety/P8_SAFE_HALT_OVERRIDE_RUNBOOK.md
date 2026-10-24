# P8 Safe Halt & Override Runbook

## Autonomous Halt
The `SafeHaltManager` automatically suspends all evolution and critical tool calls if:
- Safety incidents exceed 10 within a window.
- System error rate exceeds 50%.

## Manual Halt
Call `POST /safety/halt?reason=...` via the API.

## Human Takeover
To resume operations after a halt:
1. Audit the cause of the halt.
2. Resolve underlying issues.
3. Call `POST /safety/resume` via the API.
