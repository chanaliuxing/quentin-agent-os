from __future__ import annotations

from quentin.utils.json import make_jsonable


def test_make_jsonable_handles_cycles() -> None:
    d: dict = {"a": 1}
    d["self"] = d
    out = make_jsonable(d)
    assert isinstance(out, dict)
    assert out["a"] == 1
    assert isinstance(out.get("self"), dict)
    assert out["self"].get("type") == "cycle"


def test_make_jsonable_drops_problem_keys() -> None:
    class Dummy:
        def __init__(self) -> None:
            self.cancel_token = object()
            self.trace_recorder = object()
            self.keep = "ok"

    out = make_jsonable({"x": Dummy(), "cancel_token": "drop"})
    assert "cancel_token" not in out
    x = out["x"]
    assert isinstance(x, dict)
    assert x.get("keep") == "ok"
    assert "cancel_token" not in x
    assert "trace_recorder" not in x

