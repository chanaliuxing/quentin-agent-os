"""
Integration test for git commit functionality.

Verifies that the self-programming engine actually creates git commits.
"""
from __future__ import annotations

import pytest
import subprocess
from pathlib import Path

from meta_agent.self_programming.infra.git_ops import GitSafetyLayer


class TestGitIntegration:
    """Test that git operations work correctly."""

    def test_git_safety_layer_creates_sandbox(self, tmp_path):
        """Test that GitSafetyLayer can create sandbox branches."""
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)

        # Create initial commit
        test_file = tmp_path / "README.md"
        test_file.write_text("# Test Repo")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True)

        # Test GitSafetyLayer
        git = GitSafetyLayer(repo_path=str(tmp_path))
        assert git.enabled is True

        # Create sandbox
        sandbox_branch = git.create_sandbox("test_task_123")
        assert sandbox_branch.startswith("ai-dev/test_tas")

        # Verify we're on the sandbox branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == sandbox_branch

    def test_git_safety_layer_commits_work(self, tmp_path):
        """Test that GitSafetyLayer can commit changes."""
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)

        # Initial commit
        test_file = tmp_path / "README.md"
        test_file.write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True)

        # Create sandbox and make changes
        git = GitSafetyLayer(repo_path=str(tmp_path))
        sandbox_branch = git.create_sandbox("test_task")

        # Make a change
        new_file = tmp_path / "new_file.py"
        new_file.write_text("def hello():\n    return 'world'\n")

        # Commit the change
        git.commit_work("Add new_file.py")

        # Verify commit was created
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "Add new_file.py" in result.stdout

        # Verify the file is committed
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "new_file.py" in result.stdout

    def test_git_safety_layer_cleanup_sandbox(self, tmp_path):
        """Test that GitSafetyLayer cleans up sandbox branches."""
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)

        # Initial commit on main
        test_file = tmp_path / "README.md"
        test_file.write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True)

        # Get base branch name
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        base_branch = result.stdout.strip()

        # Create and cleanup sandbox
        git = GitSafetyLayer(repo_path=str(tmp_path))
        sandbox_branch = git.create_sandbox("test_cleanup")

        # Verify we're on sandbox
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == sandbox_branch

        # Cleanup
        git.cleanup_sandbox(sandbox_branch)

        # Verify we're back on base branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == base_branch

        # Verify sandbox branch is deleted
        result = subprocess.run(
            ["git", "branch"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert sandbox_branch not in result.stdout

    def test_current_repo_has_git(self):
        """Verify that the current repository has git enabled."""
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "true"

    def test_git_safety_layer_in_current_repo(self):
        """Test that GitSafetyLayer works in the current repository."""
        git = GitSafetyLayer(repo_path=".")
        assert git.enabled is True
        assert git._base_branch is not None

        # Don't actually create a sandbox in the real repo
        # Just verify the layer is functional


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
