from __future__ import annotations

import hashlib
import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class ExecSkillPlugin:
    skill_id: str
    name: str
    description: str
    entrypoint: str
    domain: str
    tags: List[str]
    dir_path: Path
    manifest_path: Path
    permissions: List[str] = field(default_factory=list)
    requires_env: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def resolve_exec_skill_dirs(repo_root: str | Path) -> List[Path]:
    root = Path(repo_root).resolve()
    override = (os.getenv("QUENTIN_EXEC_SKILLS_DIRS") or "").strip()
    if override:
        out: List[Path] = []
        for part in override.split(","):
            p = part.strip()
            if not p:
                continue
            out.append((root / p).resolve() if not Path(p).is_absolute() else Path(p).resolve())
        return out
    return [
        (root / "extensions" / "skills").resolve(),
        (root / "quentin" / "mutable" / "extensions" / "skills").resolve(),
    ]


def _parse_manifest_yaml(text: str) -> Dict[str, Any]:
    import yaml

    obj = yaml.safe_load(text or "")
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError("manifest yaml must be a mapping at top level")
    return obj


def discover_exec_skill_plugins(repo_root: str | Path) -> List[ExecSkillPlugin]:
    if not _env_bool("QUENTIN_EXEC_SKILLS_ENABLED", True):
        return []
    out: List[ExecSkillPlugin] = []
    for base in resolve_exec_skill_dirs(repo_root):
        if not base.exists():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            mf = child / "manifest.yaml"
            logic = child / "logic.py"
            if not mf.exists() or not logic.exists():
                continue
            try:
                data = _parse_manifest_yaml(mf.read_text(encoding="utf-8"))
            except Exception:
                continue
            sid = str(data.get("id") or data.get("skill_id") or child.name).strip() or child.name
            name = str(data.get("name") or sid).strip() or sid
            desc = str(data.get("description") or "").strip()
            entrypoint = str(data.get("entrypoint") or "logic:run").strip() or "logic:run"
            domain = str(data.get("domain") or "core").strip() or "core"
            tags_raw = data.get("tags")
            tags: List[str] = []
            if isinstance(tags_raw, list):
                for item in tags_raw:
                    t = str(item or "").strip()
                    if t:
                        tags.append(t)
            
            perms_raw = data.get("permissions")
            permissions: List[str] = []
            if isinstance(perms_raw, list):
                permissions = [str(p).strip() for p in perms_raw if str(p).strip()]

            env_raw = data.get("requires_env")
            requires_env: List[str] = []
            if isinstance(env_raw, list):
                requires_env = [str(e).strip() for e in env_raw if str(e).strip()]

            out.append(
                ExecSkillPlugin(
                    skill_id=sid,
                    name=name,
                    description=desc,
                    entrypoint=entrypoint,
                    domain=domain,
                    tags=tags,
                    dir_path=child,
                    manifest_path=mf,
                    permissions=permissions,
                    requires_env=requires_env,
                    meta=data if isinstance(data, dict) else {},
                )
            )
    return out


def load_exec_skill_callable(*, plugin: ExecSkillPlugin) -> Callable[..., Any]:
    if ":" not in plugin.entrypoint:
        raise ValueError("entrypoint must be '<module>:<symbol>' (e.g. logic:run)")
    mod_name, sym = plugin.entrypoint.split(":", 1)
    if mod_name != "logic":
        raise ValueError("v1 only supports logic.py entrypoints (entrypoint must start with 'logic:')")
    logic_path = plugin.dir_path / "logic.py"
    if not logic_path.exists():
        raise FileNotFoundError(f"missing logic.py in {plugin.dir_path}")

    h = hashlib.sha256(f"{plugin.dir_path}:{logic_path.stat().st_mtime}".encode("utf-8")).hexdigest()[:12]
    module_name = f"quentin_exec_skill_{plugin.dir_path.name}_{h}"
    spec = importlib.util.spec_from_file_location(module_name, str(logic_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load spec for {logic_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    fn = getattr(module, sym, None)
    if not callable(fn):
        raise AttributeError(f"entrypoint symbol not callable: {plugin.entrypoint}")
    
    def wrapped_fn(*args, **kwargs):
        if _env_bool("QUENTIN_PLUGIN_RUNTIME_ISOLATION", False):
            for env_var in plugin.requires_env:
                if not os.getenv(env_var):
                    raise RuntimeError(f"Skill {plugin.skill_id} requires environment variable {env_var} which is missing.")
        return fn(*args, **kwargs)

    return wrapped_fn


def resolve_exec_skill(repo_root: str | Path, skill_id_or_name: str) -> Optional[ExecSkillPlugin]:
    key = str(skill_id_or_name or "").strip()
    if not key:
        return None
    for sk in discover_exec_skill_plugins(repo_root):
        if sk.skill_id == key or sk.name == key:
            return sk
    return None
