import subprocess
import sys


def test_blueprint_coverage_report_runs() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/blueprint_coverage_report.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Summary:" in proc.stdout

