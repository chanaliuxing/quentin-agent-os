import sys
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict

# Mock backends
from meta_agent.self_programming.backends.base import (
    PatchApplierBackend,
    PatchStoreBackend,
    RepoAdapterBackend,
    SelfProgBackendBundle,
    TestRunnerBackend,
)
from meta_agent.self_programming.engine_v2 import SelfProgrammingEngineV2

@dataclass
class MockTestRunner:
    def run_tests(self, implementation_code: str, verification_test_code: str, target_file: Path, source_root: Path) -> Dict[str, Any]:
        print("MockTestRunner called!")
        return {"success": True, "stdout": "mock pass", "stderr": ""}

@dataclass
class MockApplier:
    def apply_patch(self, patch: Any) -> Any:
        print("MockApplier called!")
        class Result:
            is_blocked = False
            reason = None
        return Result()

@dataclass
class MockStore:
    def save_patch(self, patch: Any) -> None:
        print("MockStore called!")

@dataclass
class MockRepo:
    def create_sandbox(self, branch_name: str): return "mock-branch"
    def cleanup_sandbox(self, branch_name: str): pass
    def finalize_success(self, *args, **kwargs): pass
    @property
    def enabled(self): return True

def test_mock_backend():
    bundle = SelfProgBackendBundle(
        test_runner=MockTestRunner(),
        patch_applier=MockApplier(),
        patch_store=MockStore(),
        repo_adapter=MockRepo(),
    )
    
    engine = SelfProgrammingEngineV2(backend_bundle=bundle)
    
    # Verify injection
    assert engine.test_runner == bundle.test_runner
    assert engine._applier == bundle.patch_applier
    assert engine.patch_store == bundle.patch_store
    assert engine.git == bundle.repo_adapter
    
    # Try calling test runner via engine logic (we can't easily run full engine flow without complex setup,
    # but we can verify the method call if we could invoke _run_for_single_gap, but that's async and complex)
    # Instead, let's just check the property access which we did above.
    
    print("SelfProgrammingEngineV2 successfully accepted backend bundle.")

if __name__ == "__main__":
    try:
        test_mock_backend()
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
