import pytest
from quentin.tools.middleware.quality_gate import QualityGateMiddleware
from quentin.tools.schemas import ToolCallResult
from unittest.mock import MagicMock

def test_quality_gate_non_python(tmp_path):
    gate = QualityGateMiddleware(repo_root=str(tmp_path))
    result = ToolCallResult(tool_name="fs.write_file", success=True, output={"status": "ok"})
    
    # Should skip for non-python files
    after = gate.after(tool_name="fs.write_file", params={"path": "test.txt"}, result=result, ctx=None)
    assert after.result.success is True

def test_quality_gate_invalid_python(tmp_path):
    gate = QualityGateMiddleware(repo_root=str(tmp_path))
    py_file = tmp_path / "broken.py"
    py_file.write_text("if True:\n    print('fail' \n") # Syntax error (missing parenthesis)
    
    result = ToolCallResult(tool_name="fs.write_file", success=True, output={"status": "ok"})
    
    after = gate.after(tool_name="fs.write_file", params={"path": "broken.py"}, result=result, ctx=None)
    
    # Static check (ruff) should find the error
    assert after.result.success is False
    assert "Quality gate failed" in after.result.error

def test_quality_gate_valid_python(tmp_path):
    gate = QualityGateMiddleware(repo_root=str(tmp_path))
    py_file = tmp_path / "valid.py"
    py_file.write_text("def hello():\n    print('hello')\n")
    
    result = ToolCallResult(tool_name="fs.write_file", success=True, output={"status": "ok"})
    
    after = gate.after(tool_name="fs.write_file", params={"path": "valid.py"}, result=result, ctx=None)
    assert after.result.success is True
