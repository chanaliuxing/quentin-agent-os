# Project Quentin Refactoring Roadmap

This document outlines the refactoring plan to align the codebase with the architectural vision described in `docs/ARCHITECTURE.md`. The current codebase is heavily fragmented and duplicated, and this roadmap will guide the process of cleaning it up.

## Phase 1: Deduplication and Consolidation

The first phase focuses on removing redundant files and directories and consolidating related functionality into single, well-defined modules.

- [x] **`eval` vs. `evaluation`:** Merge the contents of `quentin/evaluation` into `quentin/eval` and remove the `quentin/evaluation` directory.
- [x] **`self_programming` vs. `selfprog`:** Merge the contents of `quentin/selfprog` into `quentin/self_programming` and remove the `quentin/selfprog` directory.
- [x] **Cognitive Loop:** Consolidate the cognitive loop logic into `quentin/cognitive/loop.py` and remove the redundant files from `quentin/base` and `quentin/core` (legacy paths are removed).
- [x] **Model Router:** Refactor the various router implementations (`quentin/models/router.py`, `quentin/llm/data_driven_router.py`, `quentin/llm/router_deprecated.py`) into a single, unified `quentin/routing/model_router.py` (legacy paths re-export the canonical router).
- [x] **Sleep Loop:** Consolidate the sleep loop logic into `quentin/sleep/loop.py` and remove the redundant files from `quentin/loops` and `quentin/memory` (legacy paths are now thin compatibility wrappers).

## Phase 2: Reorganization

The second phase focuses on aligning the file structure with the documented architecture.

- [x] **Reorganize `quentin/research`:** Move the contents of the `quentin/research` directory into the appropriate L1, L2, or L3 layers, and remove the `quentin/research` directory (moved to `quentin/l3/research`).
- [x] **Reorganize `quentin/base` and `quentin/core`:** Move the remaining files from `quentin/base` and `quentin/core` into the appropriate architectural layers and remove these directories (base removed; core removed).

## Phase 3: Documentation Update

The final phase focuses on updating the documentation to reflect the changes made during the refactoring process.

- [x] **Update `docs/ARCHITECTURE.md`:** Update the architecture document to reflect any necessary compromises and changes made during implementation.
- [x] **Update `docs/CONFIG_AND_EXTEND.md`:** Update the configuration and extension guide to reflect the new, unified `ModelRouter`.
- [x] **Create new documentation:** Create new documentation for any new components or modules that were created during the refactoring process.
