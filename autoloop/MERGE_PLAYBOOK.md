# AutoLoop Merge Playbook (Risk-Controlled)

## Goal
Merge AutoLoop framework changes to `main` while keeping the commit set reviewable and runnable after each step.

## Pre-check
```bash
git fetch --all --prune
cd .
git checkout -b codex/autoloop-release origin/main
```

## Batch 1: Runtime foundation (must pass first)
Apply only executable core + packaging:
```bash
git checkout integration/autoloop -- autoloop/app
git checkout integration/autoloop -- autoloop/pyproject.toml autoloop/run.py autoloop/quickstart.sh
git add autoloop/app autoloop/pyproject.toml autoloop/run.py autoloop/quickstart.sh
git commit -m "autoloop: import runtime core and packaging"
```
Validate:
```bash
cd autoloop && pytest tests/unit -q || true
python -m app.main --help
```

## Batch 2: Contracts and tests
```bash
cd .
git checkout integration/autoloop -- autoloop/schemas autoloop/tests
git add autoloop/schemas autoloop/tests
git commit -m "autoloop: add contracts and test suites"
```
Validate:
```bash
cd autoloop && pytest tests -q
```

## Batch 3: Minimal docs and ops metadata
```bash
cd .
git checkout integration/autoloop -- autoloop/README.md autoloop/CHANGELOG.md autoloop/AGENTS.md
git add autoloop/README.md autoloop/CHANGELOG.md autoloop/AGENTS.md
git commit -m "autoloop: add canonical documentation"
```

## Batch 4: Optional architecture docs (manual approval)
Only include if release requires full design context:
```bash
git checkout integration/autoloop -- autoloop/RFC-001-AUTOLOOP-V2-CONVERGENCE.md autoloop/RFC-002-AUTOLOOP-V2-IMPLEMENTATION.md autoloop/RFC-003-PHASE-1-FOUNDATION.md
git add autoloop/RFC-*.md
git commit -m "autoloop: add architecture RFC set"
```

## Explicitly excluded in this release
- `autoloop_nbai/**`
- Root-level unrelated modifications outside `autoloop/**`
- Generated analysis/summary markdown and demo output artifacts

## Final gate before merge
```bash
cd ./autoloop
pytest tests -q
python -m app.main health
```

## Merge
```bash
cd .
git checkout main
git pull --ff-only
git merge --no-ff codex/autoloop-release
```
