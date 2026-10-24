from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_check_memory_runtime_tiers_script_passes_with_valid_config(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = tmp_path / "tiers.json"
    cfg.write_text(
        json.dumps(
            {
                "online": {"max_records": 100, "active_window_days": 30},
                "offline": {"min_records": 101},
            }
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "check_memory_runtime_tiers.py"),
            "--config",
            str(cfg),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr[-2000:] + "\n" + proc.stdout[-2000:]


def test_check_memory_runtime_tiers_script_fails_on_invalid_boundary(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = tmp_path / "tiers_bad.json"
    cfg.write_text(
        json.dumps(
            {
                "online": {"max_records": 100, "active_window_days": 30},
                "offline": {"min_records": 100},
            }
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "check_memory_runtime_tiers.py"),
            "--config",
            str(cfg),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
