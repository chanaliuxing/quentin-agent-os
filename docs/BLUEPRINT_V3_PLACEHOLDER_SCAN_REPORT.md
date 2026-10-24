# Blueprint v3: Placeholder Scan Report (Codebase)

Date: 2026-02-07

Purpose:
- Provide an explicit inventory of remaining "placeholder-like" markers in code/docs.
- Separate **intentional abstract interfaces** (acceptable) from **actionable runtime placeholders** (should be burned down).

Method (best-effort):
- Grep patterns: `NotImplementedError`, `raise NotImplementedError`, `placeholder`, `FIXME`, `TODO:`
- Then manually classify whether the placeholder is:
  - `interface`: abstract base class / Protocol / docs example (acceptable)
  - `runtime`: code path likely to be exercised by runtime/CLI/tests (actionable)

## Summary

As of 2026-02-07:
- Blueprint v3 tracking subset is fully runnable:
  - `python -m quentin.cli.qctl blueprint-scan --emit-evidence` -> 10/10 green
- Remaining placeholder markers are dominated by **interfaces** and **docs**, not by the runtime critical path.

## Actionable (Runtime) Placeholders

None detected on the canonical L3->L2->L1 loop path (feedback loops, blueprint tooling, memory fabric, safety kernel).

If you want to push further, the next candidates to harden are:
- `meta_agent/llm/client.py` (`LLMClient.generate`): currently an abstract interface only; decide whether to delete or implement a stub backend.
- `quentin/orchestrator/core.py` (`LanguageModel.generate`): abstract interface; safe to keep unless wired into runtime.

## Intentional Interfaces / Docs

These are acceptable as-is (they are interfaces or documentation stubs), and should not block "blueprint v3 runnable":
- `meta_agent/llm/client.py`: interface-only (NotImplementedError)
- `quentin/orchestrator/core.py`: interface-only (NotImplementedError)
- `meta_agent/SELF_PROGRAMMING.md`: documentation examples with NotImplementedError

## Suggested Next Step (If You Want “Zero Placeholder Tokens”)

- Decide a repo policy:
  - Option A: allow interface placeholders (`NotImplementedError`) but ban runtime placeholders in non-abstract classes.
  - Option B: ban all `NotImplementedError` and replace with explicit feature-flagged `RuntimeError("disabled")`.

