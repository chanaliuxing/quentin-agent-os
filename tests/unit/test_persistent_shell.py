from __future__ import annotations

from pathlib import Path

from quentin.infra.utils.persistent_shell import StatefulShell


def test_stateful_shell_persists_cd(tmp_path: Path) -> None:
    d = tmp_path / "work"
    d.mkdir(parents=True, exist_ok=True)
    sh = StatefulShell(cwd=str(tmp_path))
    out1, code1 = sh.run(f"cd {d}")
    assert code1 == 0
    assert out1 == ""
    out2, code2 = sh.run("pwd")
    assert code2 == 0
    assert str(d) in out2


def test_stateful_shell_persists_export_and_unset() -> None:
    sh = StatefulShell()
    _, c1 = sh.run("export Q_PERSIST_HELLO=world")
    assert c1 == 0
    out, c2 = sh.run("echo $Q_PERSIST_HELLO")
    assert c2 == 0
    assert "world" in out
    _, c3 = sh.run("unset Q_PERSIST_HELLO")
    assert c3 == 0
    out2, c4 = sh.run("echo $Q_PERSIST_HELLO")
    assert c4 == 0
    # echo empty var returns newline only.
    assert out2.strip() == ""

