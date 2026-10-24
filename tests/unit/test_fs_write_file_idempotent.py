import pytest
import os
from unittest.mock import MagicMock, patch
from pathlib import Path
from quentin.tools.filesystem import fs_write_file

def test_fs_write_file_skip_if_unchanged(tmp_path):
    # Setup
    test_file = tmp_path / "test.txt"
    content = "hello world"
    test_file.write_text(content)
    
    # Mock dependencies
    with patch("quentin.tools.filesystem._get_repo_root", return_value=tmp_path):
        with patch("quentin.tools.filesystem._resolve_for_write", return_value=test_file):
            # First call with same content
            params = {"path": "test.txt", "content": content}
            res = fs_write_file(params)
            
            assert res["status"] == "ok"
            assert res["result"] == "unchanged_skipped"
            assert res.get("skipped") is True
            
            # Second call with different content
            new_content = "something else"
            params = {"path": "test.txt", "content": new_content}
            res = fs_write_file(params)
            
            assert res["status"] == "ok"
            assert "written" in res["result"]
            assert res.get("skipped") is not True
            assert test_file.read_text() == new_content

def test_fs_write_file_manifest_validation(tmp_path):
    # Setup
    test_file = tmp_path / "manifest.yaml"
    
    with patch("quentin.tools.filesystem._get_repo_root", return_value=tmp_path):
        with patch("quentin.tools.filesystem._resolve_for_write", return_value=test_file):
            # Invalid manifest (missing keys)
            content = "id: my_tool\nname: My Tool"
            params = {"path": "manifest.yaml", "content": content}
            res = fs_write_file(params)
            
            assert res["status"] == "error"
            assert "Manifest validation failed" in res["error"]
            assert not test_file.exists()
            
            # Valid manifest
            content = """
id: my_tool
name: My Tool
description: desc
entrypoint: logic:run
kind: tool
domain: core
risk_level: medium
output_trust: untrusted
permissions: []
"""
            params = {"path": "manifest.yaml", "content": content}
            res = fs_write_file(params)
            
            assert res["status"] == "ok"
            assert "written" in res["result"]
            assert test_file.exists()
