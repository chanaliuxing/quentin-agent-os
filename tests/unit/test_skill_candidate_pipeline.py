from __future__ import annotations

from quentin.skills.candidate_pipeline import SkillCandidate, SandboxPytestRunner


def test_skill_candidate_sandbox_pytest_runner(tmp_path) -> None:
    # Candidate must expose run_skill(params) returning dict.
    impl = """
from __future__ import annotations

from typing import Any, Dict


def run_skill(params: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "echo": params.get("x")}
""".lstrip()

    test_code = """
from __future__ import annotations

from candidate_pkg.skill_skill import run_skill


def test_run_skill_echo():
    out = run_skill({"x": 123})
    assert out["ok"] is True
    assert out["echo"] == 123
""".lstrip()

    cand = SkillCandidate(
        candidate_id="cand_123",
        name="skill",
        domain="core",
        implementation_code=impl,
        verification_test_code=test_code,
    )

    runner = SandboxPytestRunner(repo_root=tmp_path)
    report = runner.run(cand, timeout_sec=60)
    assert report.ok, f"stdout={report.stdout}\nstderr={report.stderr}"
