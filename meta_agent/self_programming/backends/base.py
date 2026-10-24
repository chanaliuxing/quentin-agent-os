from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable
from pathlib import Path
from dataclasses import dataclass, field

@runtime_checkable
class TestRunnerBackend(Protocol):
    def run_tests(self, implementation_code: str, verification_test_code: str, target_file: Path, source_root: Path) -> Dict[str, Any]:
        """
        Run verification tests for the generated implementation.
        Returns dict with keys: success (bool), stdout (str), stderr (str).
        """
        ...

@runtime_checkable
class PatchApplierBackend(Protocol):
    def apply_patch(self, patch: Any) -> Any:
        """
        Apply the patch proposal to the codebase (safely).
        Returns a result object with .is_blocked, .reason properties.
        """
        ...

@runtime_checkable
class PatchStoreBackend(Protocol):
    def save_patch(self, patch: Any) -> None:
        """
        Persist the patch proposal.
        """
        ...

@runtime_checkable
class RepoAdapterBackend(Protocol):
    """
    Abstracts git or version control operations.
    """
    @property
    def enabled(self) -> bool: ...

    def create_sandbox(self, branch_name: str) -> Optional[str]: ...
    
    def cleanup_sandbox(self, branch_name: str) -> None: ...
    
    def finalize_success(self, branch_name: str, commit_message: str, merge: bool = True, delete_branch: bool = True) -> None: ...

@dataclass
class SelfProgBackendBundle:
    """
    A bundle of backends required for the self-programming engine.
    """
    test_runner: TestRunnerBackend
    patch_applier: PatchApplierBackend
    patch_store: PatchStoreBackend
    repo_adapter: RepoAdapterBackend
    extra: Dict[str, Any] = field(default_factory=dict)
