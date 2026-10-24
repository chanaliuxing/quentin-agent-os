from __future__ import annotations

from quentin.governance.constitution import Constitution


def test_constitution_load_from_yaml(tmp_path):
    p = tmp_path / "governance.yaml"
    p.write_text("policies:\n  max_tokens: 123\n", encoding="utf-8")

    c = Constitution.load(p)
    assert c.get("policies")["max_tokens"] == 123
