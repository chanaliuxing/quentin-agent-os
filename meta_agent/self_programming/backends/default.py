from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from meta_agent.self_programming.backends.base import (
    PatchApplierBackend,
    PatchStoreBackend,
    RepoAdapterBackend,
    SelfProgBackendBundle,
    TestRunnerBackend,
)
from meta_agent.self_programming.test_runner import SandboxTestRunner
from meta_agent.patches.safe_applier import SafePatchApplier
from meta_agent.patches.store import PatchStore
from meta_agent.self_programming.infra.git_ops import GitSafetyLayer

class DefaultTestRunnerAdapter(TestRunnerBackend):
    def __init__(self, runner: SandboxTestRunner):
        self._runner = runner

    def run_tests(self, implementation_code: str, verification_test_code: str, target_file: Path, source_root: Path) -> Dict[str, Any]:
        return self._runner.run_in_sandbox(
            implementation_code=implementation_code,
            verification_test_code=verification_test_code,
            target_file=target_file,
            source_root=source_root
        )

# SafePatchApplier, PatchStore, GitSafetyLayer match the protocol signatures closely enough 
# or are used directly in the engine.
# However, to be strict with the backend protocol, we should adapt them if method names differ.
# SafePatchApplier.apply_patch(patch) -> ok.
# PatchStore.save_patch(patch) -> ok.
# GitSafetyLayer methods match RepoAdapterBackend.

def build_default_bundle(repo_root: Path, safety_kernel: Any = None) -> SelfProgBackendBundle:
    test_runner = DefaultTestRunnerAdapter(SandboxTestRunner())
    applier = SafePatchApplier(repo_root=repo_root, safety_kernel=safety_kernel)
    store = PatchStore(path=str(repo_root / "data" / "patches.json"))
    git_layer = GitSafetyLayer(repo_path=str(repo_root))
    
    return SelfProgBackendBundle(
        test_runner=test_runner,
        patch_applier=applier, # type: ignore
        patch_store=store,     # type: ignore
        repo_adapter=git_layer # type: ignore
    )
