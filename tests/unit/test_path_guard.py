import pytest
from pathlib import Path
import tempfile
import shutil
import os

from quentin.kernel.path_guard import PathGuard

class TestPathGuard:
    @pytest.fixture(autouse=True)
    def setup_repo(self):
        # Create a temporary directory that acts as repo_root
        self.tmpdir = Path(tempfile.mkdtemp())
        self.repo_root = self.tmpdir
        
        # Create some dummy directories to test against
        (self.repo_root / "mutable" / "skills").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "quentin" / "kernel").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "quentin" / "tools").mkdir(parents=True, exist_ok=True)
        
        yield
        
        shutil.rmtree(self.tmpdir)

    def test_allowed_path_success(self, setup_repo):
        guard = PathGuard(self.repo_root, allowed_roots=["mutable/skills"])
        allowed_path = guard.ensure_allowed_path("mutable/skills/test.py")
        assert allowed_path == (self.repo_root / "mutable" / "skills" / "test.py").resolve()

    def test_forbidden_path_denied(self, setup_repo):
        # Default allowed_roots are conservative write areas.
        guard = PathGuard(self.repo_root) 
        with pytest.raises(ValueError, match="Target file 'quentin/kernel/safety.py' is not under allowed roots"):
            guard.ensure_allowed_path("quentin/kernel/safety.py")

    def test_path_traversal_attack(self, setup_repo):
        guard = PathGuard(self.repo_root)
        with pytest.raises(ValueError, match="Target file outside repo_root"):
            guard.ensure_allowed_path("../../etc/passwd")

    def test_absolute_path_denied(self, setup_repo):
        guard = PathGuard(self.repo_root)
        with pytest.raises(ValueError, match="Absolute path not allowed"):
            guard.ensure_allowed_path(str(self.repo_root / "mutable" / "test.py"))

    def test_default_allowed_roots(self, setup_repo):
        # Test with default allowed_roots
        guard = PathGuard(self.repo_root)
        
        # Should allow mutable/
        assert guard.ensure_allowed_path("mutable/my_file.py") == (self.repo_root / "mutable" / "my_file.py").resolve()
        
        # Should allow quentin/skills/
        (self.repo_root / "quentin" / "skills").mkdir(parents=True, exist_ok=True)
        assert guard.ensure_allowed_path("quentin/skills/my_skill.py") == (self.repo_root / "quentin" / "skills" / "my_skill.py").resolve()

        # Should allow generated/
        (self.repo_root / "generated").mkdir(parents=True, exist_ok=True)
        assert guard.ensure_allowed_path("generated/report.md") == (self.repo_root / "generated" / "report.md").resolve()
        
        # Should allow meta_agent/tools/
        (self.repo_root / "meta_agent" / "tools").mkdir(parents=True, exist_ok=True)
        assert guard.ensure_allowed_path("meta_agent/tools/my_tool.py") == (self.repo_root / "meta_agent" / "tools" / "my_tool.py").resolve()

        # Should allow quentin/mutable/ (back-compat for self-programming targets)
        (self.repo_root / "quentin" / "mutable").mkdir(parents=True, exist_ok=True)
        assert guard.ensure_allowed_path("quentin/mutable/no_marker.py") == (self.repo_root / "quentin" / "mutable" / "no_marker.py").resolve()

        # Should allow extensions/tools/ (tool plugin root)
        (self.repo_root / "extensions" / "tools").mkdir(parents=True, exist_ok=True)
        assert guard.ensure_allowed_path("extensions/tools/demo/manifest.yaml") == (self.repo_root / "extensions" / "tools" / "demo" / "manifest.yaml").resolve()

        # Should deny quentin/config/
        (self.repo_root / "quentin" / "config").mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError, match="Target file 'quentin/config/settings.py' is not under allowed roots"):
            guard.ensure_allowed_path("quentin/config/settings.py")

    def test_extra_allowed_roots_from_env(self, setup_repo, monkeypatch):
        monkeypatch.setenv("QUENTIN_PATH_GUARD_EXTRA_ALLOWED_ROOTS", "quentin/execution,docs/runbooks")
        guard = PathGuard(self.repo_root)
        assert guard.ensure_allowed_path("quentin/execution/verify.log") == (
            self.repo_root / "quentin" / "execution" / "verify.log"
        ).resolve()
        assert guard.ensure_allowed_path("docs/runbooks/plan.md") == (
            self.repo_root / "docs" / "runbooks" / "plan.md"
        ).resolve()

    def test_allowed_root_prefix_is_not_loose_match(self, setup_repo):
        guard = PathGuard(self.repo_root, allowed_roots=["mutable"])
        with pytest.raises(ValueError, match="not under allowed roots"):
            guard.ensure_allowed_path("mutablex/file.txt")
