from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest


def test_check_champion_env_strict_fails_when_not_ready(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["QDRANT_URL"] = "http://127.0.0.1:1"
    env["PG_DSN"] = "postgresql://postgres:postgres@127.0.0.1:1/quentin_memory"
    env["QUENTIN_QDRANT_TIMEOUT_S"] = "0.2"

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "check_champion_env.py"),
            "--strict",
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 5, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
    assert "not_ready" in proc.stdout
    assert "qdrant" in proc.stdout
    assert "postgres" in proc.stdout


def test_check_champion_env_strict_passes_with_ready_qdrant_and_psycopg_stub(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    qdrant_url = "http://127.0.0.1:6333"
    try:
        req = urllib.request.Request(f"{qdrant_url}/readyz", method="GET")
        with urllib.request.urlopen(req, timeout=0.5) as resp:
            if int(getattr(resp, "status", 0) or 0) != 200:
                pytest.skip("Local qdrant /readyz is not ready.")
    except Exception:
        pytest.skip("Local qdrant is not reachable; skip champion success-path test.")

    stub_pkg = tmp_path / "psycopg"
    stub_pkg.mkdir(parents=True, exist_ok=True)
    (stub_pkg / "__init__.py").write_text(
        """
class _Cur:
    def fetchone(self):
        return (1,)

class _Conn:
    def execute(self, _sql):
        return _Cur()
    def close(self):
        return None

def connect(*_args, **_kwargs):
    return _Conn()
""".lstrip(),
        encoding="utf-8",
    )

    env = dict(os.environ)
    old_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(tmp_path) + (os.pathsep + old_pp if old_pp else "")
    env["QDRANT_URL"] = qdrant_url
    env["PG_DSN"] = "postgresql://stub:stub@127.0.0.1:5432/stubdb"

    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "check_champion_env.py"),
            "--strict",
        ],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]
    assert "status" in proc.stdout
    assert "'status': 'ok'" in proc.stdout or '"status": "ok"' in proc.stdout
