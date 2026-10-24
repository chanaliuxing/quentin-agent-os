import pytest
from pathlib import Path
import tempfile
import shutil
from app.config import settings


@pytest.fixture
def temp_project_dir():
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_prd(temp_project_dir):
    prd_file = temp_project_dir / "prd.md"
    prd_file.write_text("""# Sample PRD

## Overview
This is a test project.

## Requirements
- Feature A
- Feature B
""")
    return prd_file


@pytest.fixture
def mock_settings(temp_project_dir, monkeypatch):
    monkeypatch.setattr(settings, "project_root", temp_project_dir)
    monkeypatch.setattr(settings, "agent_runner_type", "mock")
    monkeypatch.setattr(settings, "gate_compile_command", "true")
    monkeypatch.setattr(settings, "gate_unit_test_command", "true")
    monkeypatch.setattr(settings, "gate_integration_test_command", "true")
    monkeypatch.setattr(settings, "gate_regression_test_command", "true")
    monkeypatch.setattr(settings, "gate_static_scan_command", "true")
    monkeypatch.setattr(settings, "gate_benchmark_command", "")
    monkeypatch.setattr(settings, "wait_node_max_cycles", 1)
    settings.ensure_dirs()
    return settings
