from __future__ import annotations

from pathlib import Path

from scripts import run_canary_brain_once as mod


class _DummyDaemon:
    def __init__(self, report: dict):
        self._report = report

    def run_once(self, *, input_text: str, metadata: dict | None = None) -> dict:
        _ = input_text
        _ = metadata
        return dict(self._report)


def _base_report() -> dict:
    return {
        "task_id": "t1",
        "goal_id": "g1",
        "done": True,
        "done_confidence": 1.0,
        "patchflow_report": {"processed": 0},
    }


def test_canary_acceptance_expect_file_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "repo_root", tmp_path)
    monkeypatch.setattr(mod, "brain_daemon_from_env", lambda: _DummyDaemon(_base_report()))
    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(mod, "_local_ollama_preflight", lambda **kwargs: (True, "ollama_ready:qwen3.5:9b"))
    monkeypatch.setattr(
        mod.sys,
        "argv",
        [
            "run_canary_brain_once.py",
            "--timeout-sec",
            "0",
            "--heartbeat-sec",
            "0",
            "--expect-file",
            "generated/missing.txt",
        ],
    )
    rc = mod.main()
    assert rc == 3


def test_canary_acceptance_expect_file_content_ok(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "repo_root", tmp_path)
    target = tmp_path / "generated" / "ok.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("OK", encoding="utf-8")
    monkeypatch.setattr(mod, "brain_daemon_from_env", lambda: _DummyDaemon(_base_report()))
    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(mod, "_local_ollama_preflight", lambda **kwargs: (True, "ollama_ready:qwen3.5:9b"))
    monkeypatch.setattr(
        mod.sys,
        "argv",
        [
            "run_canary_brain_once.py",
            "--timeout-sec",
            "0",
            "--heartbeat-sec",
            "0",
            "--expect-file",
            "generated/ok.txt",
            "--expect-file-content",
            "OK",
        ],
    )
    rc = mod.main()
    assert rc == 0


def test_apply_base_env_overrides_shell_timeouts(monkeypatch) -> None:
    monkeypatch.setenv("QUENTIN_LLM_TIMEOUT_LOCAL_S", "420")
    monkeypatch.setenv("QUENTIN_COUNCIL_LOCAL_MEMBER_TIMEOUT_S", "420")
    monkeypatch.setenv("QUENTIN_REFLECTION_ENABLED", "1")

    mod._apply_base_env()

    assert mod.os.environ["QUENTIN_LLM_TIMEOUT_LOCAL_S"] == "420"
    assert mod.os.environ["QUENTIN_COUNCIL_MEMBER_TIMEOUT_S"] == "180"
    assert mod.os.environ["QUENTIN_COUNCIL_ARBITER_TIMEOUT_S"] == "420"
    assert mod.os.environ["QUENTIN_COUNCIL_LOCAL_MEMBER_TIMEOUT_S"] == "420"
    assert mod.os.environ["QUENTIN_COUNCIL_LOCAL_ARBITER_TIMEOUT_S"] == "900"
    assert mod.os.environ["QUENTIN_REFLECTION_ENABLED"] == "0"
    assert mod.os.environ["QUENTIN_DONE_COUNCIL_ENABLED"] == "0"
    assert mod.os.environ["QUENTIN_ENABLE_PRE_SENSING"] == "0"
    assert mod.os.environ["QUENTIN_BRAIN_RUN_SLEEP"] == "0"
    assert mod.os.environ["QUENTIN_BRAIN_RUN_IMMUNE"] == "0"


def test_local_ollama_preflight_accepts_present_model(monkeypatch) -> None:
    class _Resp:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return False

        def read(self) -> bytes:
            return b'{"models":[{"name":"qwen3.5:9b"}]}'

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *args, **kwargs: _Resp())

    ok, detail = mod._local_ollama_preflight(base_url="http://localhost:11434", model="qwen3.5:9b")

    assert ok is True
    assert detail == "ollama_ready:qwen3.5:9b"


def test_local_ollama_preflight_rejects_missing_model(monkeypatch) -> None:
    class _Resp:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return False

        def read(self) -> bytes:
            return b'{"models":[{"name":"qwen3.5:4b"}]}'

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *args, **kwargs: _Resp())

    ok, detail = mod._local_ollama_preflight(base_url="http://localhost:11434", model="qwen3.5:9b")

    assert ok is False
    assert detail == "ollama_model_missing:qwen3.5:9b"
