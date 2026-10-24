from __future__ import annotations

import os

from quentin.infra.env_manager import EnvManager


def test_env_manager_maps_legacy_routing_policy_plugins(monkeypatch) -> None:
    monkeypatch.delenv("QUENTIN_ROUTING_POLICY", raising=False)
    monkeypatch.setenv("QUENTIN_ROUTING_POLICY_PLUGINS", "1")

    mgr = EnvManager()
    mgr.normalize()

    assert mgr is not None
    assert os.getenv("QUENTIN_ROUTING_POLICY") == "default"
