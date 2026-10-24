from pathlib import Path

from app.workspace import split_claimed_paths, validate_claimed_paths


def test_validate_claimed_paths_accepts_allowed_matches():
    result = validate_claimed_paths(
        claimed_paths=["app/core/main.py", "app/module_main/service.py"],
        allowed_patterns=["app/**/*.py"],
        repo_root=Path.cwd(),
    )
    assert result.ok is True
    assert result.invalid_paths == []


def test_validate_claimed_paths_rejects_out_of_scope_changes():
    result = validate_claimed_paths(
        claimed_paths=["README.md", "runtime/logs/phase_01.log"],
        allowed_patterns=["app/**/*.py"],
        repo_root=Path.cwd(),
    )
    assert result.ok is False
    assert "README.md" in result.invalid_paths


def test_validate_claimed_paths_ignores_non_source_artifacts():
    result = validate_claimed_paths(
        claimed_paths=[
            "app/core/main.py",
            "phases/phase_01/results/module_main_dev.md",
            "runtime/evidence/run/phase_01/execution_summary.json",
        ],
        allowed_patterns=["app/**/*.py"],
        repo_root=Path.cwd(),
    )
    assert result.ok is True
    assert result.invalid_paths == []
    assert "phases/phase_01/results/module_main_dev.md" in result.ignored_paths
    assert "runtime/evidence/run/phase_01/execution_summary.json" in result.ignored_paths


def test_split_claimed_paths_separates_source_and_artifacts():
    filtered, ignored = split_claimed_paths(
        claimed_paths=[
            "app/module_main/pipeline.py",
            "tests/unit/test_module_main_pipeline.py",
            "phases/phase_01/results/module_main_dev.md",
        ],
        repo_root=Path.cwd(),
    )
    assert filtered == [
        "app/module_main/pipeline.py",
        "tests/unit/test_module_main_pipeline.py",
    ]
    assert ignored == ["phases/phase_01/results/module_main_dev.md"]
