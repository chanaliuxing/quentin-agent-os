from __future__ import annotations

import json
import logging
import random
import subprocess
from pathlib import Path
from typing import Dict, List, Literal, Optional

from meta_agent.self_programming.schema import ProgrammingTask
from meta_agent.self_programming.metrics_store import MetricsStoreProtocol

logger = logging.getLogger(__name__)


class SimpleEvolutionStrategyManager:
    """
    v0.1 strategy manager: retry failed tasks using MetricsStore logs.
    """

    def __init__(self, metrics_store: MetricsStoreProtocol) -> None:
        self.metrics_store = metrics_store

    def generate_tasks(self, limit: int = 10) -> List[ProgrammingTask]:
        failed_runs = self.metrics_store.get_runs_by_status("test_fail", limit=limit)
        retry_tasks: List[ProgrammingTask] = []
        for run in failed_runs:
            task_id = run.get("task_id", "")
            if "retry_of" in task_id:
                continue

            payload = run.get("task_payload") or {}
            description = payload.get("description") or "Previous attempt failed."
            errors = run.get("raw_test_output") or ""

            retry_tasks.append(
                ProgrammingTask(
                    task_id=f"retry_of_{task_id}",
                    origin=payload.get("origin", "bugfix"),
                    description=f"Previous attempt failed. Analyze test errors and fix.\nErrors:\n{errors}",
                    repo_root=payload.get("repo_root", "."),
                    related_files=payload.get("related_files", []),
                    context_summary=payload.get("context_summary", description),
                    constraints=payload.get("constraints", {}),
                    acceptance_criteria=payload.get("acceptance_criteria", []),
                )
            )
        return retry_tasks


StrategyType = Literal["retry_failed", "find_untested_code", "find_complex_code", "blueprint_gap"]


class EvolutionStrategyManager:
    """
    v0.2: Multi-strategy manager with weighted selection.

    Strategies:
    - retry_failed: React to test_fail (existing SimpleEvolutionStrategyManager logic)
    - find_untested_code: Proactively add tests to uncovered modules
    - find_complex_code: Refactor high-complexity functions
    - blueprint_gap: Implement missing blueprint requirements
    """

    def __init__(
        self,
        metrics_store: MetricsStoreProtocol,
        repo_root: str = ".",
        strategy_weights: Optional[Dict[StrategyType, float]] = None,
        coverage_threshold: float = 0.80,
        complexity_threshold: int = 10,
        blueprint_path: Optional[str] = None,
    ) -> None:
        self.metrics_store = metrics_store
        self.repo_root = Path(repo_root).resolve()
        self.weights = strategy_weights or {
            "retry_failed": 0.5,
            "find_untested_code": 0.2,
            "find_complex_code": 0.15,
            "blueprint_gap": 0.15,
        }
        self.blueprint_path = blueprint_path
        self.coverage_threshold = coverage_threshold
        self.complexity_threshold = complexity_threshold

        # Validate weights sum to ~1.0
        total = sum(self.weights.values())
        if not (0.99 <= total <= 1.01):
            logger.warning("Strategy weights sum to %.2f, expected ~1.0", total)

    def generate_tasks(self, limit: int = 10) -> List[ProgrammingTask]:
        """
        Generate tasks using weighted random selection of strategies.

        Returns up to `limit` tasks total across all strategies.
        """
        all_tasks: List[ProgrammingTask] = []

        # Calculate how many tasks from each strategy
        strategy_limits = self._allocate_limits(limit)

        for strategy, strategy_limit in strategy_limits.items():
            if strategy_limit <= 0:
                continue

            try:
                if strategy == "retry_failed":
                    tasks = self._generate_retry_failed_tasks(limit=strategy_limit)
                elif strategy == "find_untested_code":
                    tasks = self._generate_untested_code_tasks(limit=strategy_limit)
                elif strategy == "find_complex_code":
                    tasks = self._generate_complex_code_tasks(limit=strategy_limit)
                elif strategy == "blueprint_gap":
                    tasks = self._generate_blueprint_gap_tasks(limit=strategy_limit)
                else:
                    logger.warning("Unknown strategy: %s", strategy)
                    continue

                all_tasks.extend(tasks)
            except Exception:
                logger.exception("Failed to generate tasks for strategy: %s", strategy)

        # Shuffle to avoid always prioritizing one strategy
        random.shuffle(all_tasks)
        return all_tasks[:limit]

    def _allocate_limits(self, total_limit: int) -> Dict[StrategyType, int]:
        """Allocate task limits to each strategy based on weights."""
        allocated: Dict[StrategyType, int] = {}
        remaining = total_limit

        # Sort by weight descending to allocate largest first
        sorted_strategies = sorted(
            self.weights.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        for strategy, weight in sorted_strategies:
            strategy_limit = int(total_limit * weight)
            allocated[strategy] = min(strategy_limit, remaining)
            remaining -= allocated[strategy]

        # Distribute any remainder
        if remaining > 0:
            for strategy, _ in sorted_strategies:
                if remaining <= 0:
                    break
                allocated[strategy] += 1
                remaining -= 1

        return allocated

    def _generate_retry_failed_tasks(self, limit: int) -> List[ProgrammingTask]:
        """
        Retry failed tasks (same logic as SimpleEvolutionStrategyManager).
        """
        failed_runs = self.metrics_store.get_runs_by_status("test_fail", limit=limit)
        retry_tasks: List[ProgrammingTask] = []

        for run in failed_runs:
            task_id = run.get("task_id", "")
            if "retry_of" in task_id:
                continue

            payload = run.get("task_payload") or {}
            description = payload.get("description") or "Previous attempt failed."
            errors = run.get("raw_test_output") or ""

            retry_tasks.append(
                ProgrammingTask(
                    task_id=f"retry_of_{task_id}",
                    origin="bugfix",
                    description=f"Previous attempt failed. Analyze test errors and fix.\nErrors:\n{errors}",
                    repo_root=str(self.repo_root),
                    related_files=payload.get("related_files", []),
                    context_summary=payload.get("context_summary", description),
                    constraints=payload.get("constraints", {}),
                    acceptance_criteria=payload.get("acceptance_criteria", []),
                )
            )

        return retry_tasks

    def _generate_untested_code_tasks(self, limit: int) -> List[ProgrammingTask]:
        """
        Find modules with low test coverage and generate test-writing tasks.

        Uses pytest-cov to analyze coverage.
        """
        try:
            # Run pytest with coverage
            result = subprocess.run(
                [
                    "python",
                    "-m",
                    "pytest",
                    "--cov=meta_agent",
                    "--cov=quentin",
                    "--cov-report=json",
                    "--cov-report=term-missing",
                    "-q",
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=60,
            )

            coverage_file = self.repo_root / "coverage.json"
            if not coverage_file.exists():
                logger.warning("coverage.json not found after pytest run")
                return []

            with coverage_file.open("r") as f:
                coverage_data = json.load(f)

            # Find files with coverage below threshold
            files = coverage_data.get("files", {})
            low_coverage_files = []

            for file_path, file_data in files.items():
                summary = file_data.get("summary", {})
                percent_covered = summary.get("percent_covered", 100.0)

                if percent_covered < self.coverage_threshold * 100:
                    low_coverage_files.append(
                        {
                            "file": file_path,
                            "coverage": percent_covered,
                            "missing_lines": file_data.get("missing_lines", []),
                        }
                    )

            # Sort by lowest coverage first
            low_coverage_files.sort(key=lambda x: x["coverage"])

            # Generate tasks
            tasks: List[ProgrammingTask] = []
            for item in low_coverage_files[:limit]:
                file_path = item["file"]
                coverage_pct = item["coverage"]
                missing_lines = item["missing_lines"]

                # Convert absolute path to relative
                try:
                    rel_path = Path(file_path).relative_to(self.repo_root)
                except ValueError:
                    rel_path = Path(file_path)

                task_id = f"add_tests_{rel_path.as_posix().replace('/', '_')}_{int(coverage_pct)}"

                tasks.append(
                    ProgrammingTask(
                        task_id=task_id,
                        origin="refactor",
                        description=(
                            f"Add tests for {rel_path}\n"
                            f"Current coverage: {coverage_pct:.1f}%\n"
                            f"Target: {self.coverage_threshold * 100:.0f}%\n"
                            f"Missing lines: {missing_lines[:10]}"  # Show first 10
                        ),
                        repo_root=str(self.repo_root),
                        related_files=[str(rel_path)],
                        context_summary=f"Low test coverage detected: {coverage_pct:.1f}%",
                        constraints={"type": "test_coverage"},
                        acceptance_criteria=[
                            f"Coverage for {rel_path} >= {self.coverage_threshold * 100:.0f}%",
                            "All tests pass",
                        ],
                    )
                )

            logger.info(
                "Generated %d untested_code tasks (found %d files below %.0f%%)",
                len(tasks),
                len(low_coverage_files),
                self.coverage_threshold * 100,
            )
            return tasks

        except subprocess.TimeoutExpired:
            logger.warning("pytest --cov timed out")
            return []
        except Exception:
            logger.exception("Failed to generate untested_code tasks")
            return []

    def _generate_complex_code_tasks(self, limit: int) -> List[ProgrammingTask]:
        """
        Find functions with high cyclomatic complexity and generate refactoring tasks.

        Uses radon to analyze complexity.
        """
        try:
            # Run radon cc (cyclomatic complexity)
            result = subprocess.run(
                [
                    "radon",
                    "cc",
                    "meta_agent/",
                    "quentin/",
                    "-s",  # Show complexity score
                    "-a",  # Average at end
                    "-j",  # JSON output
                ],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.warning("radon cc failed: %s", result.stderr)
                return []

            complexity_data = json.loads(result.stdout)

            # Collect high-complexity functions
            complex_functions = []

            for file_path, functions in complexity_data.items():
                if not isinstance(functions, list):
                    continue

                for func in functions:
                    complexity = func.get("complexity", 0)
                    if complexity > self.complexity_threshold:
                        complex_functions.append(
                            {
                                "file": file_path,
                                "name": func.get("name", "unknown"),
                                "complexity": complexity,
                                "lineno": func.get("lineno", 0),
                                "rank": func.get("rank", ""),
                            }
                        )

            # Sort by highest complexity first
            complex_functions.sort(key=lambda x: x["complexity"], reverse=True)

            # Generate tasks
            tasks: List[ProgrammingTask] = []
            for item in complex_functions[:limit]:
                file_path = item["file"]
                func_name = item["name"]
                complexity = item["complexity"]
                lineno = item["lineno"]
                rank = item["rank"]

                # Convert to relative path
                try:
                    rel_path = Path(file_path).relative_to(self.repo_root)
                except ValueError:
                    rel_path = Path(file_path)

                task_id = f"refactor_complex_{rel_path.as_posix().replace('/', '_')}_{func_name}_{complexity}"

                tasks.append(
                    ProgrammingTask(
                        task_id=task_id,
                        origin="refactor",
                        description=(
                            f"Refactor high-complexity function: {func_name}\n"
                            f"Location: {rel_path}:{lineno}\n"
                            f"Cyclomatic complexity: {complexity} (rank {rank})\n"
                            f"Target: Reduce to <{self.complexity_threshold}\n"
                            f"Suggested approaches:\n"
                            f"- Extract helper functions\n"
                            f"- Simplify conditional logic\n"
                            f"- Use early returns"
                        ),
                        repo_root=str(self.repo_root),
                        related_files=[str(rel_path)],
                        context_summary=f"High cyclomatic complexity detected: {complexity}",
                        constraints={"type": "refactoring", "preserve_behavior": True},
                        acceptance_criteria=[
                            f"Complexity of {func_name} < {self.complexity_threshold}",
                            "All existing tests pass",
                            "No behavior changes",
                        ],
                    )
                )

            logger.info(
                "Generated %d complex_code tasks (found %d functions > %d)",
                len(tasks),
                len(complex_functions),
                self.complexity_threshold,
            )
            return tasks

        except subprocess.TimeoutExpired:
            logger.warning("radon cc timed out")
            return []
        except json.JSONDecodeError:
            logger.exception("Failed to parse radon JSON output")
            return []
        except Exception:
            logger.exception("Failed to generate complex_code tasks")
            return []

    def _generate_blueprint_gap_tasks(self, limit: int) -> List[ProgrammingTask]:
        """
        Generate tasks for implementing blueprint gaps.
        Uses BlueprintGapTrackerV2 to find missing/incomplete implementations.
        """
        if not self.blueprint_path:
            logger.warning("No blueprint path configured, skipping blueprint_gap strategy")
            return []

        try:
            from meta_agent.blueprint.gap_tracker import BlueprintGapTrackerV2, GapType
            from meta_agent.blueprint.model import BlueprintDocument

            # Load blueprint
            blueprint_file = Path(self.blueprint_path)
            if not blueprint_file.exists():
                logger.warning("Blueprint file not found: %s", blueprint_file)
                return []

            # Load blueprint (simplified - real implementation would use proper loader)
            with open(blueprint_file, "r") as f:
                import json
                blueprint_data = json.load(f)

            # Create blueprint document (simplified)
            # In real usage, would use proper BlueprintDocument loader
            blueprint = BlueprintDocument.from_dict(blueprint_data)

            # Analyze gaps
            tracker = BlueprintGapTrackerV2(blueprint)
            gaps = tracker.analyze()

            # Generate tasks from gaps
            tasks: List[ProgrammingTask] = []
            for gap in gaps[:limit]:
                task_id = f"blueprint_gap_{gap.clause_id}_{gap.gap_type.value}"

                if gap.gap_type == GapType.NOT_IMPLEMENTED:
                    origin = "blueprint_gap"
                    description = (
                        f"Implement missing blueprint requirement: {gap.clause_id}\n"
                        f"{gap.details}\n"
                        f"This capability is defined in the blueprint but not yet implemented."
                    )
                    criteria = [
                        f"Implement {gap.clause_id}",
                        "Add tests for new implementation",
                        "Update blueprint references",
                    ]
                elif gap.gap_type == GapType.IMPLEMENTED_NO_TESTS:
                    origin = "experiment"
                    description = (
                        f"Add tests for blueprint requirement: {gap.clause_id}\n"
                        f"{gap.details}\n"
                        f"Implementation exists but lacks test coverage."
                    )
                    criteria = [
                        f"Add comprehensive tests for {gap.clause_id}",
                        "Achieve >80% coverage for implementation",
                    ]
                else:  # IMPLEMENTED_BUT_UNSTABLE
                    origin = "bugfix"
                    description = (
                        f"Stabilize unstable blueprint implementation: {gap.clause_id}\n"
                        f"{gap.details}\n"
                        f"Implementation exists but shows instability in recent metrics."
                    )
                    criteria = [
                        f"Fix stability issues in {gap.clause_id}",
                        "Reduce error rate to <5%",
                        "Add defensive error handling",
                    ]

                tasks.append(
                    ProgrammingTask(
                        task_id=task_id,
                        origin=origin,
                        description=description,
                        repo_root=str(self.repo_root),
                        related_files=gap.implementation_refs or [],
                        context_summary=f"Blueprint gap: {gap.gap_type.value}",
                        constraints={"blueprint_clause": gap.clause_id},
                        acceptance_criteria=criteria,
                    )
                )

            logger.info(
                "Generated %d blueprint_gap tasks from %d total gaps",
                len(tasks),
                len(gaps),
            )
            return tasks

        except ImportError:
            logger.warning("Blueprint tracker not available, skipping blueprint_gap strategy")
            return []
        except Exception:
            logger.exception("Failed to generate blueprint_gap tasks")
            return []
