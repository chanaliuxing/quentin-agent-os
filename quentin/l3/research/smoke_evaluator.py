"""
Smoke Test Evaluator for Patch Application.

Provides a simple interface for running smoke tests (pytest -q subset)
and logging results with timings.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import logging
import subprocess
import time
from quentin.utils.time import now_iso

logger = logging.getLogger(__name__)
from quentin.runtime.session_write_lock import acquire_session_write_lock


@dataclass
class SmokeTestResult:
    """
    Result of running smoke tests.

    - success: Whether all tests passed
    - test_count: Number of tests run
    - passed_count: Number of tests that passed
    - failed_count: Number of tests that failed
    - skipped_count: Number of tests skipped
    - duration_ms: Total test duration in milliseconds
    - output: Test output (stdout + stderr)
    - timestamp: When test was run
    - test_files: List of test files that were run
    """
    success: bool
    test_count: int
    passed_count: int
    failed_count: int
    skipped_count: int
    duration_ms: float
    output: str
    timestamp: str
    test_files: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SmokeEvaluator:
    """
    Smoke test evaluator for quick validation.

    Runs a subset of tests (smoke tests) to quickly validate
    that basic functionality works.
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        log_path: Optional[str | Path] = None,
        timeout_seconds: int = 60,
    ):
        """
        Initialize smoke evaluator.

        Args:
            repo_root: Root directory of the repository
            log_path: Optional path to log results (JSONL format)
            timeout_seconds: Timeout for test execution
        """
        self.repo_root = Path(repo_root).resolve()
        self.timeout_seconds = timeout_seconds

        if log_path is None:
            self.log_path = self.repo_root / "data" / "eval" / "smoke_tests.jsonl"
        else:
            self.log_path = Path(log_path)

        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def run_smoke_tests(
        self,
        *,
        test_paths: Optional[List[str]] = None,
        markers: Optional[List[str]] = None,
    ) -> SmokeTestResult:
        """
        Run smoke tests.

        Args:
            test_paths: List of test paths to run (default: tests/unit)
            markers: Pytest markers to filter tests (e.g., ["smoke", "fast"])

        Returns:
            SmokeTestResult with test outcomes and timings
        """
        if test_paths is None:
            test_paths = ["tests/unit"]

        # Build pytest command
        cmd = ["pytest", "-q", "--tb=short"]

        # Add markers if provided
        if markers:
            for marker in markers:
                cmd.extend(["-m", marker])

        # Add test paths
        cmd.extend(test_paths)

        # Add verbose output to capture test counts
        cmd.append("-v")

        logger.info(f"Running smoke tests: {' '.join(cmd)}")

        start_time = time.perf_counter()
        timestamp = now_iso()

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            output = result.stdout + "\n" + result.stderr

            # Parse pytest output to extract counts
            counts = self._parse_pytest_output(output)

            smoke_result = SmokeTestResult(
                success=(result.returncode == 0),
                test_count=counts["total"],
                passed_count=counts["passed"],
                failed_count=counts["failed"],
                skipped_count=counts["skipped"],
                duration_ms=duration_ms,
                output=output,
                timestamp=timestamp,
                test_files=test_paths,
            )

            logger.info(
                f"Smoke tests {'passed' if smoke_result.success else 'FAILED'}: "
                f"{smoke_result.passed_count}/{smoke_result.test_count} passed "
                f"in {smoke_result.duration_ms:.1f}ms"
            )

            self._log_result(smoke_result)

            return smoke_result

        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            logger.error(f"Smoke tests timed out after {self.timeout_seconds}s")

            smoke_result = SmokeTestResult(
                success=False,
                test_count=0,
                passed_count=0,
                failed_count=0,
                skipped_count=0,
                duration_ms=duration_ms,
                output=f"Tests timed out after {self.timeout_seconds} seconds",
                timestamp=timestamp,
                test_files=test_paths,
            )

            self._log_result(smoke_result)

            return smoke_result

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            logger.exception("Error running smoke tests")

            smoke_result = SmokeTestResult(
                success=False,
                test_count=0,
                passed_count=0,
                failed_count=0,
                skipped_count=0,
                duration_ms=duration_ms,
                output=f"Error: {e}",
                timestamp=timestamp,
                test_files=test_paths,
            )

            self._log_result(smoke_result)

            return smoke_result

    def _parse_pytest_output(self, output: str) -> Dict[str, int]:
        """
        Parse pytest output to extract test counts.

        Looks for lines like:
        - "5 passed in 0.23s"
        - "3 passed, 2 failed in 1.45s"
        - "10 passed, 2 skipped in 0.56s"

        Returns dict with: total, passed, failed, skipped
        """
        counts = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
        }

        # Look for the summary line at the end
        lines = output.strip().split("\n")

        for line in reversed(lines):
            line = line.strip().lower()

            # Look for pytest summary format
            if "passed" in line or "failed" in line or "skipped" in line:
                # Extract numbers
                import re

                # Match patterns like "5 passed", "2 failed", etc.
                passed_match = re.search(r"(\d+)\s+passed", line)
                failed_match = re.search(r"(\d+)\s+failed", line)
                skipped_match = re.search(r"(\d+)\s+skipped", line)

                if passed_match:
                    counts["passed"] = int(passed_match.group(1))
                if failed_match:
                    counts["failed"] = int(failed_match.group(1))
                if skipped_match:
                    counts["skipped"] = int(skipped_match.group(1))

                counts["total"] = counts["passed"] + counts["failed"] + counts["skipped"]

                # Found the summary, stop searching
                if counts["total"] > 0:
                    break

        return counts

    def _log_result(self, result: SmokeTestResult) -> None:
        """
        Log result to JSONL file.

        Args:
            result: SmokeTestResult to log
        """
        try:
            lock = acquire_session_write_lock(session_file=self.log_path)
            try:
                with self.log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
            finally:
                lock["release"]()

            logger.debug(f"Logged smoke test result to {self.log_path}")
        except Exception:
            logger.exception("Failed to log smoke test result")

    def get_recent_results(self, limit: int = 10) -> List[SmokeTestResult]:
        """
        Get recent smoke test results from log.

        Args:
            limit: Maximum number of results to return

        Returns:
            List of recent SmokeTestResult objects
        """
        if not self.log_path.exists():
            return []

        results = []

        try:
            with self.log_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()

            # Get last N lines
            for line in lines[-limit:]:
                try:
                    data = json.loads(line.strip())
                    results.append(SmokeTestResult(**data))
                except Exception:
                    logger.exception("Failed to parse smoke test result")

            return results

        except Exception:
            logger.exception("Failed to read smoke test log")
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get overall statistics from logged results.

        Returns:
            Dict with statistics (total runs, success rate, avg duration, etc.)
        """
        recent = self.get_recent_results(limit=100)

        if not recent:
            return {
                "total_runs": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "avg_test_count": 0.0,
            }

        total_runs = len(recent)
        successes = sum(1 for r in recent if r.success)
        total_duration = sum(r.duration_ms for r in recent)
        total_tests = sum(r.test_count for r in recent)

        return {
            "total_runs": total_runs,
            "success_rate": successes / total_runs if total_runs > 0 else 0.0,
            "avg_duration_ms": total_duration / total_runs if total_runs > 0 else 0.0,
            "avg_test_count": total_tests / total_runs if total_runs > 0 else 0.0,
            "recent_success_count": successes,
            "recent_failure_count": total_runs - successes,
        }
