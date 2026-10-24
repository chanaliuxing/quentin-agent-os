# AutoLoop Release Scope Decision (for merge to main)

## Keep in release branch
- Core runtime and control loop: `autoloop/app/**`
- Contracts/specs: `autoloop/schemas/**`
- Runtime templates/prompts: `autoloop/templates/**`, `autoloop/prompts/**`
- Executables and packaging: `autoloop/run.py`, `autoloop/quickstart.sh`, `autoloop/pyproject.toml`
- Canonical docs: `autoloop/README.md`, `autoloop/CHANGELOG.md`, `autoloop/AGENTS.md`
- Validation assets: `autoloop/tests/**`

## Keep only if explicitly needed
- Design/RFC docs: `autoloop/RFC-*.md`
- Operational guides: `autoloop/CLI_RUNNERS_GUIDE.md`, `autoloop/SESSION_AUTO_MANAGEMENT.md`

## Exclude from mainline by default
- Generated analysis/report docs: `autoloop/*SUMMARY*.md`, `autoloop/*ANALYSIS*.md`, `autoloop/DRY_RUN_REPORT.md`, `autoloop/FINAL_SUMMARY.md`, `autoloop/VERIFICATION_CHECKLIST.md`, `autoloop/TODO_TOP_TIER_GAPS.md`
- Example/demo outputs: `autoloop/outputproduct/**`, `autoloop/src/junk/**`, `autoloop/*_prd.md`, `autoloop/prd.md`, `autoloop/prd_example.md`
- Parallel sandbox copy: `autoloop_nbai/**`
- Unrelated root changes outside `autoloop/**` (unless separately reviewed)

## Rationale
- Mainline should receive executable framework + tests first.
- Large generated docs and demo artifacts increase merge risk and review cost.
- `autoloop_nbai/**` appears to be a duplicated workspace and should not be merged into core path.
