import json
from pathlib import Path

from meta_agent.self_programming.auditing.auditor import BlueprintAuditor


def write_spec(tmpdir: Path, module_hint: str, symbols_expected=None):
    spec = {
        "requirements": [
            {
                "id": "req1",
                "title": "Test req",
                "module_hint": module_hint,
                "symbols_expected": symbols_expected or [],
            }
        ]
    }
    (tmpdir / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    return tmpdir / "spec.json"


def test_method_match_and_missing(tmp_path: Path):
    # create file with class but missing method
    code = """
class VectorStore:
    def add(self): pass
"""
    (tmp_path / "vec.py").write_text(code, encoding="utf-8")
    spec = write_spec(tmp_path, "vec.py", ["VectorStore.search"])

    auditor = BlueprintAuditor(str(tmp_path))
    results, warnings, errors = auditor.audit_spec(str(spec))
    assert not errors
    assert results[0].missing_items  # should list missing method
    assert results[0].status in ("partial", "unknown", "gap")


def test_placeholder_penalty(tmp_path: Path):
    code = """
def foo():
    \"\"\"TODO implement\"\"\"
    pass
"""
    (tmp_path / "mod.py").write_text(code, encoding="utf-8")
    spec = write_spec(tmp_path, "mod.py", ["foo"])
    auditor = BlueprintAuditor(str(tmp_path))
    results, warnings, errors = auditor.audit_spec(str(spec))
    assert not errors
    assert results[0].status != "implemented"


def test_strong_evidence_required(tmp_path: Path):
    code = """
# just a file with no defs
value = 1
"""
    (tmp_path / "plain.py").write_text(code, encoding="utf-8")
    spec = write_spec(tmp_path, "plain.py", [])
    auditor = BlueprintAuditor(str(tmp_path))
    results, warnings, errors = auditor.audit_spec(str(spec))
    assert results[0].status in ("unknown", "gap")
