from pathlib import Path

from app.metrics.runner_health import bump_runner_health, read_runner_health


def test_runner_health_bump_and_read(tmp_path: Path):
    runtime_dir = tmp_path / "runtime"
    payload = bump_runner_health("state_db_fallback_count", runtime_dir=runtime_dir)
    assert payload["state_db_fallback_count"] == 1
    loaded = read_runner_health(runtime_dir=runtime_dir)
    assert loaded["state_db_fallback_count"] == 1
    assert loaded["last_event"] == "state_db_fallback_count"
