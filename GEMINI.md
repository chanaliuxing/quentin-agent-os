# Project Taylor (Quentin) Foundational Mandates

These instructions are foundational mandates for Gemini CLI while working on Project Taylor. They take absolute precedence over any general workflows.

## 1. Code Integrity & Non-Destructive Engineering
*   **No Unsolicited Deletions**: NEVER delete existing scripts (`.py`, `.sh`, `.json`, etc.) or debugging assets (like `reproduce_issue.py`) unless explicitly requested by the user.
*   **Functional Density Conservation**: It is strictly forbidden to delete functional code blocks, fields, or parameters just to bypass errors (e.g., `TypeError`, `IndentationError`, `ImportError`).
*   **Fix via Extension, Not Removal**: If a model mismatch or API change causes a crash, fix it by extending the data model, adding default values, or creating compatibility shims. Deletion is the last resort and requires confirmation.
*   **Git Audit**: After every change, perform a `git diff` to ensure no critical logic was accidentally removed.

## 2. Foundational Tool Protection (`verify_system.py`)
*   **Foundational Status**: `verify_system.py` is a persistent, foundational testing utility.
*   **No Overwriting**: Never overwrite its core logic (e.g., the canonical `WebSearchTool` task) or its established environment configuration.
*   **Task Switching**: If a new testing objective is required (e.g., "Tool Mastery Test"), create a separate file (e.g., `verify_mastery.py`) or ask the user for permission to modify the original in-place.

## 3. Mandatory Validation & Regression Cycle
Every code modification must follow this strict **Plan -> Act -> Validate** cycle:
1.  **Surgical Change**: Apply minimal, targeted modifications.
2.  **Unit Verification**: Create or run a specific test script to verify the new logic.
3.  **Regression Testing**: ALWAYS run the regression suite (e.g., `python3 tests/regression_suite.py`) to ensure system-wide stability (Memory, Security, Tools, Billing).
4.  **Final Git Check**: Run `git status` and `git diff --stat` to confirm the change is additive or refining, not destructive.

## 4. Engineering Standards
*   **Adhere to Local Context**: Rigorously follow existing architectural patterns and naming conventions.
*   **Zero-Hallucination Sensing**: Ensure the sensing layer (`loop_context_helpers.py`) and action layer (`filesystem.py`) share identical validation schemas to prevent the brain from hallucinating task completion.
