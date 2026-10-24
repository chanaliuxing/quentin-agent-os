import json
import subprocess
from pathlib import Path


def test_brain_e2e_benchmark_script_runs(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out = tmp_path / "report.json"
    hist = tmp_path / "hist.jsonl"

    proc = subprocess.run(
        ["python", "scripts/brain_e2e_benchmark.py", "--repo-root", str(repo_root), "--runs", "1", "--seed", "0", "--output", str(out), "--history", str(hist)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["summary"]["scenario_count"] > 0
    assert "todo" in data

