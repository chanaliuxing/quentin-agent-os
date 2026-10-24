from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Optional
import json
import os
import re
import subprocess
import tempfile


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _snake(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "skill"


@dataclass
class SkillCandidate:
    """
    Blueprint v3 SkillCandidate schema (minimal, JSON-friendly).
    """

    candidate_id: str
    name: str
    domain: str
    implementation_code: str
    verification_test_code: str
    created_at: str = field(default_factory=_now_iso)
    scope: Dict[str, Any] = field(default_factory=dict)
    failure_modes: list[str] = field(default_factory=list)
    risk_notes: str = ""
    supersedes_skill_id: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateTestReport:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SkillCandidateStore:
    def __init__(self, *, path: str | Path = "data/skills/candidates.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, cand: SkillCandidate) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(cand.to_dict(), ensure_ascii=False) + "\n")

    def load_all(self) -> list[SkillCandidate]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    out.append(SkillCandidate(**data))
                except Exception:
                    continue
        return out

    def load_pending(self) -> list[SkillCandidate]:
        """Load candidates that haven't been installed/processed yet."""
        all_cands = self.load_all()
        # Heuristic: if status is not in meta, assume pending
        return [c for c in all_cands if (c.meta or {}).get("status") not in ("installed", "rejected")]


class SkillCandidateInstaller:
    """
    Auto-land a candidate as importable Python modules under `quentin/skills/generated/`.
    """

    def __init__(self, *, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()
        self.out_dir = self.repo_root / "quentin" / "skills" / "generated"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def install(self, cand: SkillCandidate) -> Dict[str, str]:
        stem = f"{_snake(cand.name)}_{_snake(cand.domain)}_{cand.candidate_id[:8]}"
        mod_path = self.out_dir / f"{stem}.py"

        # Keep the contract minimal: candidates expose `run_skill(params) -> dict`.
        mod_path.write_text(cand.implementation_code, encoding="utf-8")

        return {"module_path": str(mod_path)}


class SandboxPytestRunner:
    """
    Runs pytest for a candidate in an isolated temp directory.
    """

    def __init__(self, *, repo_root: str | Path = ".") -> None:
        self.repo_root = Path(repo_root).resolve()

    def run(self, cand: SkillCandidate, *, timeout_sec: int = 60) -> CandidateTestReport:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            pkg = td_path / "candidate_pkg"
            pkg.mkdir(parents=True, exist_ok=True)
            (pkg / "__init__.py").write_text("", encoding="utf-8")

            mod_name = f"skill_{_snake(cand.name)}"
            mod_path = pkg / f"{mod_name}.py"
            mod_path.write_text(cand.implementation_code, encoding="utf-8")

            tests_dir = td_path / "tests"
            tests_dir.mkdir(parents=True, exist_ok=True)
            test_path = tests_dir / "test_candidate.py"
            test_path.write_text(cand.verification_test_code, encoding="utf-8")

            env = dict(os.environ)
            # Ensure the candidate module is importable.
            env["PYTHONPATH"] = os.pathsep.join([str(td_path), str(self.repo_root), env.get("PYTHONPATH", "")])

            proc = subprocess.run(
                ["python", "-m", "pytest", "-q", str(test_path)],
                cwd=str(td_path),
                env=env,
                text=True,
                capture_output=True,
                timeout=max(1, int(timeout_sec)),
            )
            return CandidateTestReport(
                ok=proc.returncode == 0,
                exit_code=int(proc.returncode),
                stdout=str(proc.stdout or ""),
                stderr=str(proc.stderr or ""),
            )

