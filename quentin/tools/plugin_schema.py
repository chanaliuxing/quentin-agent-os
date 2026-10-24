from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


OutputTrust = Literal["trusted", "untrusted"]


@dataclass
class ToolPluginCacheConfig:
    enabled: bool = False
    ttl_sec: int = 0
    key_fields: list[str] = field(default_factory=list)
    max_bytes: int = 0
    stale_while_revalidate_sec: int = 0


@dataclass
class ToolPluginManifest:
    """
    Minimal plugin manifest to allow drop-in tools.

    Expected layout:
    - <plugin_dir>/manifest.yaml
    - <plugin_dir>/logic.py
    """

    tool_id: str
    name: str
    description: str = ""
    entrypoint: str = "logic:run"
    kind: str = "external"
    domain: str = "core"
    risk_level: str = "medium"
    output_trust: OutputTrust = "untrusted"
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    requires_env: list[str] = field(default_factory=list)
    cache: ToolPluginCacheConfig = field(default_factory=ToolPluginCacheConfig)
    meta: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, *, tool_id: str, data: Dict[str, Any]) -> "ToolPluginManifest":
        if not isinstance(data, dict):
            raise ValueError("manifest must be a mapping")

        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("manifest missing required field: name")

        desc = str(data.get("description") or "").strip()
        entrypoint = str(data.get("entrypoint") or "logic:run").strip() or "logic:run"
        kind = str(data.get("kind") or "external").strip() or "external"
        domain = str(data.get("domain") or "core").strip() or "core"
        risk_level = str(data.get("risk_level") or "medium").strip().lower() or "medium"

        output_trust = str(data.get("output_trust") or "untrusted").strip().lower()
        if output_trust not in ("trusted", "untrusted"):
            output_trust = "untrusted"

        input_schema = data.get("input_schema") if isinstance(data.get("input_schema"), dict) else {}
        output_schema = data.get("output_schema") if isinstance(data.get("output_schema"), dict) else {}

        perms_raw = data.get("permissions")
        permissions: list[str] = []
        if isinstance(perms_raw, list):
            permissions = [str(p).strip() for p in perms_raw if str(p).strip()]

        env_raw = data.get("requires_env")
        requires_env: list[str] = []
        if isinstance(env_raw, list):
            requires_env = [str(e).strip() for e in env_raw if str(e).strip()]

        cache_obj = data.get("cache") if isinstance(data.get("cache"), dict) else {}
        cache_enabled = bool(cache_obj.get("enabled", False))
        try:
            cache_ttl = int(cache_obj.get("ttl_sec") or 0)
        except Exception:
            cache_ttl = 0
        key_fields_raw = cache_obj.get("key_fields")
        key_fields: list[str] = []
        if isinstance(key_fields_raw, list):
            for item in key_fields_raw:
                field_name = str(item or "").strip()
                if field_name:
                    key_fields.append(field_name)
        try:
            max_bytes = int(cache_obj.get("max_bytes") or 0)
        except Exception:
            max_bytes = 0
        swr = cache_obj.get("stale_while_revalidate_sec")
        if swr is None:
            swr = cache_obj.get("stale_while_revalidate")
        try:
            stale_while_revalidate_sec = int(swr or 0)
        except Exception:
            stale_while_revalidate_sec = 0

        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}

        return cls(
            tool_id=str(tool_id),
            name=name,
            description=desc,
            entrypoint=entrypoint,
            kind=kind,
            domain=domain,
            risk_level=risk_level,
            output_trust=output_trust,  # type: ignore[assignment]
            input_schema=dict(input_schema),
            output_schema=dict(output_schema),
            permissions=permissions,
            requires_env=requires_env,
            cache=ToolPluginCacheConfig(
                enabled=cache_enabled,
                ttl_sec=max(0, cache_ttl),
                key_fields=key_fields,
                max_bytes=max(0, max_bytes),
                stale_while_revalidate_sec=max(0, stale_while_revalidate_sec),
            ),
            meta=dict(meta),
        )

    def validate(self) -> None:
        if ":" not in self.entrypoint:
            raise ValueError("entrypoint must be in form '<module>:<symbol>' (e.g. logic:run)")
        mod, sym = self.entrypoint.split(":", 1)
        if not mod or not sym:
            raise ValueError("entrypoint must be in form '<module>:<symbol>' (e.g. logic:run)")


def parse_manifest_yaml(text: str) -> Dict[str, Any]:
    import yaml

    obj = yaml.safe_load(text or "")
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError("manifest yaml must be a mapping at top level")
    return obj
