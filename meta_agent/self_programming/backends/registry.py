from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from meta_agent.self_programming.backends.base import SelfProgBackendBundle, TestRunnerBackend
from meta_agent.self_programming.backends.default import build_default_bundle


class NoopTestRunner(TestRunnerBackend):
    """
    Test runner backend that skips tests.
    This is intentionally conservative: it does not claim correctness, it just avoids blocking
    flows that only want proposal generation.
    """

    def run_tests(self, implementation_code: str, verification_test_code: str, target_file: Path, source_root: Path) -> Dict[str, Any]:  # noqa: ARG002
        return {
            "success": True,
            "skipped": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "message": "tests skipped by QUENTIN_SELFPROG_BACKEND=no_tests",
        }


def build_bundle_by_id(*, backend_id: str, repo_root: Path, safety_kernel: Any = None) -> SelfProgBackendBundle:
    """
    Backend selection for self-programming (Blueprint v3 P2-B).
    Canonical env: QUENTIN_SELFPROG_BACKEND=default|no_tests|...
    """
    bid = (backend_id or "default").strip().lower()
    base = build_default_bundle(repo_root=repo_root, safety_kernel=safety_kernel)

    if bid in ("", "default", "all"):
        base.extra = {**(base.extra or {}), "backend_id": "default"}  # type: ignore[attr-defined]
        return base

    if bid in ("no_tests", "skip_tests"):
        return SelfProgBackendBundle(
            test_runner=NoopTestRunner(),
            patch_applier=base.patch_applier,
            patch_store=base.patch_store,
            repo_adapter=base.repo_adapter,
            extra={**(base.extra or {}), "backend_id": "no_tests"},
        )

    # Unknown selection: fail-safe to default.
    base.extra = {**(base.extra or {}), "backend_id": "default"}  # type: ignore[attr-defined]
    return base


__all__ = ["build_bundle_by_id"]
