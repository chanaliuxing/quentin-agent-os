
import pytest
import os
from unittest.mock import MagicMock, patch
from pathlib import Path
from quentin.cognitive.loop_impl import CognitiveLoop
from quentin.cognitive.loop import CognitiveTask

def test_infer_pre_sensing_focus_paths(tmp_path):
    loop = CognitiveLoop(repo_root=tmp_path)
    
    # Task mentioning gemini_cli
    task = CognitiveTask(input_text="Implement gemini_cli tool", domain="core")
    
    # Create the dir so it's found
    target = tmp_path / "extensions" / "tools" / "gemini_cli"
    target.mkdir(parents=True)
    
    paths = loop._infer_pre_sensing_focus_paths(task)
    assert any("gemini_cli" in p for p in paths)


def test_infer_pre_sensing_focus_paths_includes_explicit_root_files(tmp_path):
    loop = CognitiveLoop(repo_root=tmp_path)
    (tmp_path / "AGENTS.md").write_text("repo rules", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")

    task = CognitiveTask(
        input_text="Inspect AGENTS.md and pyproject.toml, then create generated/report.txt",
        domain="core",
    )

    paths = loop._infer_pre_sensing_focus_paths(task)

    assert "AGENTS.md" in paths
    assert "pyproject.toml" in paths

def test_generate_sensing_report(tmp_path):
    loop = CognitiveLoop(repo_root=tmp_path)
    
    # Create a dummy file
    test_dir = tmp_path / "extensions" / "tools" / "test_tool"
    test_dir.mkdir(parents=True)
    manifest = test_dir / "manifest.yaml"
    manifest.write_text("id: test_tool", encoding="utf-8")
    
    task = CognitiveTask(input_text="test", domain="core")
    report = loop._generate_sensing_report(task, ["extensions/tools/test_tool"])
    
    assert "system_policies" in report
    assert "allowed_write_roots" in report["system_policies"]
    assert len(report["evidence"]) > 0
    
    evidence = report["evidence"][0]
    assert evidence["path"] == "extensions/tools/test_tool"
    assert evidence["exists"] is True
    
    # Test file within dir
    report2 = loop._generate_sensing_report(task, ["extensions/tools/test_tool/manifest.yaml"])
    evidence2 = report2["evidence"][0]
    assert evidence2["exists"] is True
    assert "hash" in evidence2
    assert "snippet" in evidence2
    assert "id: test_tool" in evidence2["snippet"]
