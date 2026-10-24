from pathlib import Path
import json

import os

from meta_agent.tools.registry_loader import (
    default_registry_index_paths,
    load_first_available,
    load_registry_index,
    resolve_registry_index,
)


def test_load_registry_index(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    data = [{"server_id": "s1", "tools": []}]
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_registry_index(path)
    assert loaded == data


def test_resolve_registry_index_prefers_inline() -> None:
    inline = [{"server_id": "inline"}]
    assert resolve_registry_index(inline, None) == inline


def test_default_registry_paths_env_override(monkeypatch, tmp_path) -> None:
    p = tmp_path / "reg.json"
    p.write_text('[{"server_id": "env"}]', encoding="utf-8")
    monkeypatch.setenv("MCP_REGISTRY_INDEX_PATHS", str(p))

    paths = default_registry_index_paths()
    assert paths and paths[0] == p

    loaded = resolve_registry_index(None, None)
    assert loaded and loaded[0]["server_id"] == "env"


def test_load_first_available(tmp_path) -> None:
    p1 = tmp_path / "missing.json"
    p2 = tmp_path / "present.json"
    p2.write_text('[{"server_id": "p2"}]', encoding="utf-8")
    out = load_first_available([p1, p2])
    assert out and out[0]["server_id"] == "p2"
