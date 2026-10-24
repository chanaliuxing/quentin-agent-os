#!/usr/bin/env python3
"""
Patch Application MVP Script

Takes a PatchCandidate, creates a temp branch/worktree, applies the patch,
runs tests, and reports ready-to-merge status.

Usage:
    python scripts/run_patch_application.py --patch-id <id> [--dry-run] [--verbose]
    python scripts/run_patch_application.py --patch-file <path> [--dry-run] [--verbose]
"""
import argparse
import json
import logging
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add repo root to path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from quentin.kernel.schemas import PatchCandidate
from meta_agent.self_programming.infra.git_ops import GitSafetyLayer
from dataclasses import asdict

logger = logging.getLogger(__name__)


class PatchApplicationResult:
    """Result of applying and testing a patch."""

    def __init__(
        self,
        patch_id: str,
        success: bool,
        branch_name: Optional[str] = None,
        test_passed: bool = False,
        test_output: str = "",
        ready_to_merge: bool = False,
        error_message: Optional[str] = None,
        applied_at: Optional[str] = None,
    ):
        self.patch_id = patch_id
        self.success = success
        self.branch_name = branch_name
        self.test_passed = test_passed
        self.test_output = test_output
        self.ready_to_merge = ready_to_merge
        self.error_message = error_message
        self.applied_at = applied_at or datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "success": self.success,
            "branch_name": self.branch_name,
            "test_passed": self.test_passed,
            "test_output": self.test_output,
            "ready_to_merge": self.ready_to_merge,
            "error_message": self.error_message,
            "applied_at": self.applied_at,
        }


class PatchApplicationRunner:
    """Applies patches in a safe git environment and runs tests."""

    def __init__(
        self,
        repo_root: Path,
        dry_run: bool = False,
        verbose: bool = False,
    ):
        self.repo_root = repo_root
        self.dry_run = dry_run
        self.verbose = verbose
        self.git_safety = GitSafetyLayer(repo_root=repo_root)

        # Setup logging
        log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s [%(levelname)s] %(message)s',
        )

    def apply_patch(
        self,
        patch: PatchCandidate,
    ) -> PatchApplicationResult:
        """
        Apply a patch candidate in a safe branch and run tests.

        Steps:
        1. Create sandbox branch (ai-patch/<patch-id>)
        2. Apply the patch text
        3. Run tests
        4. Report if ready to merge
        """
        patch_id = patch.patch_id
        logger.info(f"Applying patch {patch_id}: {patch.description}")

        if self.dry_run:
            logger.info("[DRY RUN] Would apply patch but skipping actual changes")
            return PatchApplicationResult(
                patch_id=patch_id,
                success=True,
                branch_name=f"ai-patch/{patch_id}",
                test_passed=True,
                test_output="DRY RUN - no tests executed",
                ready_to_merge=False,
                error_message=None,
            )

        try:
            # Step 1: Create sandbox branch
            branch_name = f"ai-patch/{patch_id[:8]}"
            logger.info(f"Creating sandbox branch: {branch_name}")

            self.git_safety.create_sandbox(task_id=patch_id, base_branch="main")

            # Step 2: Apply patch
            logger.info(f"Applying patch text ({len(patch.diff_text)} characters)")

            # Write patch to temp file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.patch',
                delete=False,
            ) as f:
                f.write(patch.diff_text)
                patch_file = f.name

            try:
                # Apply using git apply
                result = subprocess.run(
                    ['git', 'apply', patch_file],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                )

                if result.returncode != 0:
                    raise RuntimeError(f"git apply failed: {result.stderr}")

                logger.info("Patch applied successfully")

                # Commit the changes
                self.git_safety.commit(
                    task_id=patch_id,
                    message=f"Apply patch: {patch.description}\n\nReason: {patch.reason}",
                )

            finally:
                # Clean up temp patch file
                Path(patch_file).unlink(missing_ok=True)

            # Step 3: Run tests
            logger.info("Running tests on patched code")
            test_result = self._run_tests_for_patch(patch)

            # Step 4: Determine if ready to merge
            ready_to_merge = test_result["passed"] and test_result["no_new_failures"]

            return PatchApplicationResult(
                patch_id=patch_id,
                success=True,
                branch_name=branch_name,
                test_passed=test_result["passed"],
                test_output=test_result["output"],
                ready_to_merge=ready_to_merge,
                error_message=None,
            )

        except Exception as e:
            logger.error(f"Failed to apply patch: {e}")

            # Clean up sandbox on failure
            try:
                self.git_safety.cleanup_sandbox(task_id=patch_id)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup sandbox: {cleanup_error}")

            return PatchApplicationResult(
                patch_id=patch_id,
                success=False,
                branch_name=None,
                test_passed=False,
                test_output="",
                ready_to_merge=False,
                error_message=str(e),
            )

    def _run_tests_for_patch(self, patch: PatchCandidate) -> Dict[str, Any]:
        """
        Run relevant tests for the patched code.

        Returns dict with:
        - passed: bool
        - no_new_failures: bool
        - output: str
        - failed_tests: list
        """
        logger.info("Running pytest on affected files")

        # Determine which tests to run based on patch target
        # For MVP, run all unit tests
        test_paths = ["tests/unit"]

        try:
            result = subprocess.run(
                ['pytest'] + test_paths + ['-q', '--tb=short', '-x'],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            passed = result.returncode == 0
            output = result.stdout + "\n" + result.stderr

            logger.info(f"Tests {'passed' if passed else 'failed'}")
            if self.verbose:
                logger.debug(f"Test output:\n{output}")

            return {
                "passed": passed,
                "no_new_failures": passed,  # For MVP, same as passed
                "output": output,
                "failed_tests": [] if passed else ["unknown"],
            }

        except subprocess.TimeoutExpired:
            logger.error("Tests timed out after 5 minutes")
            return {
                "passed": False,
                "no_new_failures": False,
                "output": "Tests timed out after 5 minutes",
                "failed_tests": ["timeout"],
            }
        except Exception as e:
            logger.error(f"Error running tests: {e}")
            return {
                "passed": False,
                "no_new_failures": False,
                "output": f"Error: {e}",
                "failed_tests": ["error"],
            }


def load_patch_candidate(patch_file: Path) -> PatchCandidate:
    """Load patch candidate from JSON file."""
    with open(patch_file) as f:
        data = json.load(f)

    # Convert to PatchCandidate
    # This is a simplified version - real implementation would handle full schema
    return PatchCandidate(
        patch_id=data.get("patch_id", "unknown"),
        description=data.get("description", ""),
        reason=data.get("reason", ""),
        diff_text=data.get("diff_text", ""),
        target_files=data.get("target_files", []),
        metadata=data.get("metadata", {}),
    )


def main():
    parser = argparse.ArgumentParser(
        description="Apply patches in a safe branch and run tests"
    )
    parser.add_argument(
        "--patch-id",
        help="Patch ID to apply (looks up from patch store)",
    )
    parser.add_argument(
        "--patch-file",
        type=Path,
        help="Path to patch candidate JSON file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if not args.patch_id and not args.patch_file:
        parser.error("Must specify either --patch-id or --patch-file")

    # Load patch
    if args.patch_file:
        logger.info(f"Loading patch from file: {args.patch_file}")
        patch = load_patch_candidate(args.patch_file)
    else:
        # Minimal patch-id support: load from PatchStore if available, otherwise error.
        try:
            from meta_agent.patches.store import PatchStore
        except Exception:
            PatchStore = None  # type: ignore

        if PatchStore is None:
            logger.error("PatchStore unavailable; please use --patch-file for now")
            return 1

        store = PatchStore()
        rec = store.get_patch(str(args.patch_id))
        if rec is None:
            logger.error("Patch id not found: %s", args.patch_id)
            return 1
        patch = PatchCandidate(
            patch_id=str(getattr(rec, "patch_id", "") or getattr(rec, "id", "") or args.patch_id),
            description=str(getattr(rec, "description", "") or ""),
            reason=str(getattr(rec, "reason", "") or ""),
            diff_text=str(getattr(rec, "diff_text", "") or getattr(rec, "patch_text", "") or ""),
            target_files=list(getattr(rec, "target_files", []) or []),
            metadata=dict(getattr(rec, "metadata", {}) or {}),
        )

    # Apply patch
    runner = PatchApplicationRunner(
        repo_root=repo_root,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    result = runner.apply_patch(patch)

    # Output result
    print("\n" + "=" * 60)
    print("Patch Application Result")
    print("=" * 60)
    print(json.dumps(result.to_dict(), indent=2))
    print("=" * 60)

    if result.ready_to_merge:
        print("\n✅ Patch is READY TO MERGE")
        print(f"   Branch: {result.branch_name}")
        print(f"   Tests: PASSED")
    elif result.success:
        print("\n⚠️  Patch applied but NOT ready to merge")
        print(f"   Branch: {result.branch_name}")
        print(f"   Tests: {'PASSED' if result.test_passed else 'FAILED'}")
    else:
        print("\n❌ Patch application FAILED")
        print(f"   Error: {result.error_message}")

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
