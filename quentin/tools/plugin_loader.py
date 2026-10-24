from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from quentin.tools.plugin_cache import ToolSqliteCache
from quentin.tools.plugin_schema import ToolPluginManifest, parse_manifest_yaml
from quentin.tools.schemas import ToolCallRequest, ToolCallResult, ToolKind, ToolSpec


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def resolve_plugin_dirs(repo_root: str | Path) -> List[Path]:
    root = Path(repo_root).resolve()
    override = (os.getenv("QUENTIN_TOOL_PLUGINS_DIRS") or "").strip()
    if override:
        out: List[Path] = []
        for part in override.split(","):
            p = part.strip()
            if not p:
                continue
            out.append((root / p).resolve() if not Path(p).is_absolute() else Path(p).resolve())
        return out
    return [
        (root / "extensions" / "tools").resolve(),
        (root / "quentin" / "mutable" / "extensions" / "tools").resolve(),
    ]


def _load_manifest(plugin_dir: Path) -> Tuple[ToolPluginManifest, Path]:
    mf = plugin_dir / "manifest.yaml"
    if not mf.exists():
        raise FileNotFoundError(f"missing manifest.yaml in {plugin_dir}")
    data = parse_manifest_yaml(mf.read_text(encoding="utf-8"))
    tool_id = str(data.get("id") or data.get("tool_id") or plugin_dir.name).strip() or plugin_dir.name
    manifest = ToolPluginManifest.from_dict(tool_id=tool_id, data=data)
    manifest.validate()
    return manifest, mf


def _load_entrypoint(plugin_dir: Path, entrypoint: str) -> Callable[..., Any]:
    mod_name, sym = entrypoint.split(":", 1)
    if mod_name != "logic":
        raise ValueError("only logic.py entrypoints are supported in v1 (entrypoint must start with 'logic:')")
    logic_path = plugin_dir / "logic.py"
    if not logic_path.exists():
        raise FileNotFoundError(f"missing logic.py in {plugin_dir}")

    # Unique module name per plugin path + mtime to support dev reload between runs.
    h = hashlib.sha256(f"{plugin_dir}:{logic_path.stat().st_mtime}".encode("utf-8")).hexdigest()[:12]
    module_name = f"quentin_tool_plugin_{plugin_dir.name}_{h}"

    spec = importlib.util.spec_from_file_location(module_name, str(logic_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load spec for {logic_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    fn = getattr(module, sym, None)
    if not callable(fn):
        raise AttributeError(f"entrypoint symbol not callable: {entrypoint}")
    return fn


def _filter_payload_for_cache(*, payload: Dict[str, Any], key_fields: List[str]) -> Dict[str, Any]:
    if not key_fields:
        return dict(payload)
    selected: Dict[str, Any] = {}
    for field in key_fields:
        if field in payload:
            selected[field] = payload[field]
    return selected


def _cache_key(*, tool_name: str, payload: Dict[str, Any], key_fields: Optional[List[str]] = None) -> str:
    payload_for_key = _filter_payload_for_cache(payload=payload, key_fields=(key_fields or []))
    try:
        s = json.dumps(payload_for_key, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        s = json.dumps({"repr": repr(payload_for_key)}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(f"{tool_name}|{s}".encode("utf-8")).hexdigest()
    return f"{tool_name}:{h}"


def discover_tool_plugins(repo_root: str | Path) -> List[Path]:
    dirs = resolve_plugin_dirs(repo_root)
    out: List[Path] = []
    for base in dirs:
        if not base.exists():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            if (child / "manifest.yaml").exists():
                out.append(child)
    return out


def is_plugin_isolation_enabled() -> bool:
    return _env_bool("QUENTIN_PLUGIN_RUNTIME_ISOLATION", False)


def register_tool_plugins(*, tool_manager: Any, repo_root: str | Path) -> Dict[str, Any]:
    """
    Discover and register tool plugins into the provided ToolManager.

    Contract for plugin entrypoint:
    - signature: fn(payload: dict, ctx: ToolCallContext) -> dict | ToolCallResult
    """
    enabled = _env_bool("QUENTIN_TOOL_PLUGINS_ENABLED", True)
    if not enabled:
        return {"enabled": False, "registered": 0, "errors": []}

    cache_path = os.getenv("QUENTIN_TOOL_CACHE_PATH", "data/tool_cache.db")
    cache = ToolSqliteCache(path=(Path(repo_root).resolve() / cache_path) if not Path(cache_path).is_absolute() else cache_path)

    registered: List[str] = []
    errors: List[Dict[str, Any]] = []

    for plugin_dir in discover_tool_plugins(repo_root):
        try:
            manifest, mf_path = _load_manifest(plugin_dir)
            entry_fn = _load_entrypoint(plugin_dir, manifest.entrypoint)

            def _handler(req: ToolCallRequest, ctx: Any = None, *, _m: ToolPluginManifest = manifest, _fn=entry_fn) -> ToolCallResult:
                payload = dict(req.payload or {})
                
                # P2-D: Capability Gating
                if is_plugin_isolation_enabled():
                    for env_var in _m.requires_env:
                        if not os.getenv(env_var):
                            return ToolCallResult(
                                tool_name=req.tool_name,
                                success=False,
                                error=f"missing_required_env:{env_var}",
                                output={"status": "error", "error": f"Plugin requires environment variable {env_var} which is missing."},
                                meta={"plugin_id": _m.tool_id}
                            )

                if _m.cache.enabled and int(_m.cache.ttl_sec or 0) > 0:
                    key = _cache_key(tool_name=_m.name, payload=payload, key_fields=_m.cache.key_fields)
                    hit = cache.get(key, allow_stale_sec=int(_m.cache.stale_while_revalidate_sec or 0))
                    if hit is not None:
                        return ToolCallResult(
                            tool_name=req.tool_name,
                            success=True,
                            output={
                                "status": "ok",
                                "cached": True,
                                "cache_stale": bool(hit.stale),
                                "result": hit.value,
                            },
                            meta={
                                "plugin_id": _m.tool_id,
                                "cache_hit": True,
                                "cache_stale": bool(hit.stale),
                                "cache_key_fields": list(_m.cache.key_fields or []),
                            },
                        )

                try:
                    res = _fn(payload, ctx)
                    if isinstance(res, ToolCallResult):
                        out = res
                    else:
                        out = ToolCallResult(tool_name=req.tool_name, success=True, output={"status": "ok", "result": res})
                except Exception as e:  # noqa: BLE001
                    out = ToolCallResult(tool_name=req.tool_name, success=False, error=str(e), output={"status": "error", "error": str(e)})

                if out.success and _m.cache.enabled and int(_m.cache.ttl_sec or 0) > 0:
                    try:
                        key = _cache_key(tool_name=_m.name, payload=payload, key_fields=_m.cache.key_fields)
                        cache.set(
                            key=key,
                            value=(out.output or {}),
                            ttl_sec=int(_m.cache.ttl_sec or 0),
                            max_bytes=int(_m.cache.max_bytes or 0),
                            namespace=_m.name,
                        )
                    except Exception:
                        pass
                out.meta.setdefault("plugin_id", _m.tool_id)
                out.meta.setdefault("plugin_dir", str(plugin_dir))
                out.meta.setdefault("manifest_path", str(mf_path))
                out.meta.setdefault("cache_key_fields", list(_m.cache.key_fields or []))
                return out

            spec = ToolSpec(
                name=manifest.name,
                description=manifest.description or f"Tool plugin: {manifest.tool_id}",
                kind=ToolKind.external if str(manifest.kind).lower() == "external" else ToolKind.builtin,
                domain=manifest.domain or "core",
                risk_level=manifest.risk_level if manifest.risk_level in ("low", "medium", "high", "critical") else "medium",
                input_schema=manifest.input_schema or {},
                output_schema=manifest.output_schema or {},
                meta={
                    "plugin": True,
                    "plugin_id": manifest.tool_id,
                    "output_trust": manifest.output_trust,
                    "permissions": list(manifest.permissions or []),
                    **(manifest.meta or {}),
                },
            )

            tool_manager.register_tool(spec, _handler)
            registered.append(manifest.name)
        except Exception as e:  # noqa: BLE001
            errors.append({"plugin_dir": str(plugin_dir), "error": str(e)})

    return {"enabled": True, "registered": len(registered), "tools": registered, "errors": errors}
