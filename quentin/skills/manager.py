from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

from quentin.infra.logging import Tracer
from quentin.infra.storage.kv_store import KVStore
from quentin.skills.exec_plugin_loader import discover_exec_skill_plugins
from quentin.skills.exec_plugin_loader import load_exec_skill_callable as load_exec_plugin_callable
from quentin.skills.exec_plugin_loader import resolve_exec_skill
from quentin.skills.registry import SkillRegistry
from quentin.skills.schema import SkillSpec, SkillStatus
from quentin.skills.skill_library import SkillLibrary
from quentin.skills.skill_markdown import load_skill_markdown_file
from quentin.skills.sop_plugin_loader import discover_sop_skills, load_sop_skill_md
from quentin.skills.backends.base import SkillBackendRegistry
from quentin.skills.backends.filesystem_sop import FileSystemSOPSkillBackend
from quentin.skills.backends.exec_plugin import ExecPluginSkillBackend
from quentin.skills.backends.legacy_registry import LegacyRegistrySkillBackend
from quentin.skills.backends.builtin_infra import BuiltinInfraSkillBackend

SKILL_STATUS_CANDIDATE = "candidate"
SKILL_STATUS_ACTIVE = "active"
SKILL_STATUS_DEPRECATED = "deprecated"


class SkillManager:
    def __init__(self, repo_root: Path | str | None = None):
        self.repo_root = self._resolve_repo_root(repo_root)
        self.kv = KVStore()
        self.tracer = Tracer()
        self.library = SkillLibrary(kv=self.kv, tracer=self.tracer)
        self.registry = SkillRegistry(path=self.repo_root / "data" / "skills.json")
        self.backend_registry = SkillBackendRegistry()
        # P2-A: Skill backend selection (Blueprint v3 canonical env: QUENTIN_SKILL_BACKEND)
        import os

        backend_mode = (os.getenv("QUENTIN_SKILL_BACKEND", "default") or "default").strip().lower()
        enabled = set()
        if backend_mode in ("", "default", "all"):
            enabled = {"legacy", "markdown", "exec", "builtin"}
        elif backend_mode in ("legacy_only", "legacy"):
            enabled = {"legacy"}
        elif backend_mode in ("markdown_only", "markdown", "sop_only", "sop"):
            enabled = {"markdown"}
        elif backend_mode in ("exec_only", "exec", "plugins_only"):
            enabled = {"exec"}
        elif backend_mode in ("builtin_only", "builtin"):
            enabled = {"builtin"}
        else:
            # Unknown config: fail-safe to legacy only to preserve baseline behavior.
            enabled = {"legacy"}

        if "legacy" in enabled:
            self.backend_registry.register(LegacyRegistrySkillBackend(registry_instance=self.registry, priority=10))
        if "markdown" in enabled:
            self.backend_registry.register(FileSystemSOPSkillBackend(repo_root=self.repo_root, priority=50))
        if "exec" in enabled:
            self.backend_registry.register(ExecPluginSkillBackend(repo_root=self.repo_root, priority=100))
        if "builtin" in enabled:
            self.backend_registry.register(BuiltinInfraSkillBackend(priority=200))
        
        self._markdown_index: List[Dict[str, Any]] = []
        self._markdown_index_ready = False

    def load_all_skills(self, tool_manager: Any) -> int:
        """
        P5: Ported from OpenClaw's dynamic skill loading.
        Scans 'quentin/skills/library' for Python files and registers them as tools.
        """
        import importlib.util
        
        library_dir = self.repo_root / "quentin" / "skills" / "library"
        if not library_dir.exists():
            return 0
            
        count = 0
        for py_file in library_dir.glob("*.py"):
            if py_file.name.startswith("__"): continue
            
            try:
                # 1. Dynamic Import
                module_name = f"quentin.skills.library.{py_file.stem}"
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if not spec or not spec.loader: continue
                
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                
                # 2. Inspect and Register
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    # Heuristic: Look for classes with 'run' and 'get_schema'
                    if hasattr(attr, 'run') and hasattr(attr, 'get_schema') and isinstance(attr, type):
                        # Instantiate
                        instance = attr()
                        schema = instance.get_schema()
                        
                        # Register with ToolManager
                        from quentin.tools.schemas import ToolSpec
                        tool_spec = ToolSpec(
                            name=schema.get("name"),
                            description=schema.get("description"),
                            input_schema=schema.get("input_schema"),
                            domain="skill"
                        )
                        tool_manager.register_tool(tool_spec, instance.run)
                        count += 1
                        logger.info(f"SkillManager: Loaded dynamic skill '{tool_spec.name}' from {py_file.name}")
                        
            except Exception as e:
                logger.error(f"SkillManager: Failed to load skill from {py_file}: {e}")
                
        return count

    @staticmethod
    def _resolve_repo_root(repo_root: Path | str | None) -> Path:
        """
        Resolve a stable repo root independent of current working directory.

        Strategy:
        1) If caller provides a path, prefer it (useful for ephemeral repos in tests),
           but normalize to the nearest real repo root if it is inside one.
        2) If not provided, fallback to this module's location (repo checkout layout).
        """
        if repo_root is None:
            return Path(__file__).resolve().parents[2]

        raw = Path(repo_root).expanduser()

        def is_repo(p: Path) -> bool:
            return (p / "pyproject.toml").exists() and (p / "quentin").exists()

        # If an absolute path is provided, treat it as an explicit sandbox root even
        # if it is not a full repo checkout (unit tests rely on this).
        if raw.is_absolute():
            candidate = raw.resolve()
            if is_repo(candidate):
                return candidate
            for parent in candidate.parents:
                if is_repo(parent):
                    return parent
            return candidate

        # If a relative path is provided (e.g. "."), don't let an unrelated chdir()
        # in another test move our repo_root; fall back to this checkout's root if
        # the resolved path isn't inside a repo.
        candidate = raw.resolve()
        if is_repo(candidate):
            return candidate
        for parent in candidate.parents:
            if is_repo(parent):
                return parent
        return Path(__file__).resolve().parents[2]

    def _refresh_markdown_index(self, domain: str | None = None) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        key = str(domain or "").strip()
        for sk in discover_sop_skills(self.repo_root):
            skill_domain = str(sk.meta.get("domain") or "core")
            if key and skill_domain not in (key, "cross"):
                continue
            items.append(
                {
                    "skill_id": sk.skill_id,
                    "name": sk.name,
                    "description": sk.description,
                    "triggers": list(sk.triggers or []),
                    "requires": list(sk.requires or []),
                    "path": str(sk.skill_md_path),
                    "plugin_dir": str(sk.dir_path),
                    "domain": skill_domain,
                    "meta": dict(sk.meta or {}),
                }
            )
        if not key:
            self._markdown_index = items
            self._markdown_index_ready = True
        return items

    @staticmethod
    def _match_markdown_score(item: Dict[str, Any], task_text: str) -> int:
        text = str(task_text or "").lower().strip()
        if not text:
            return 0

        score = 0
        for trigger in item.get("triggers") or []:
            token = str(trigger or "").lower().strip()
            if token and token in text:
                score += 3

        description = str(item.get("description") or "").lower().strip()
        for token in description.split():
            t = token.strip(",.()[]{}")
            if len(t) >= 4 and t in text:
                score += 1
        return score

    def list_markdown_skills(self, domain: str | None = None) -> List[Dict[str, Any]]:
        key = str(domain or "").strip()
        if key:
            return self._refresh_markdown_index(domain=key)
        if not self._markdown_index_ready:
            self._refresh_markdown_index()
        return list(self._markdown_index)

    def load_markdown_skill(self, skill_id_or_name: str) -> Dict[str, Any]:
        cleaned = str(skill_id_or_name or "").strip()
        if not cleaned:
            return {}

        for item in self.list_markdown_skills():
            sid = str(item.get("skill_id") or "").strip()
            name = str(item.get("name") or "").strip()
            if cleaned not in {sid, name}:
                continue
            try:
                doc = load_skill_markdown_file(Path(str(item.get("path") or "")), default_skill_id=sid)
            except Exception:
                return {}
            return {
                "skill_id": doc.skill_id,
                "name": doc.name,
                "description": doc.description,
                "triggers": list(doc.triggers or []),
                "requires": list(doc.requires or []),
                "body": doc.body,
                "path": doc.path,
                "frontmatter": dict(doc.frontmatter or {}),
            }
        return {}

    def match_markdown_skills(self, task_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        scored: List[Dict[str, Any]] = []
        for item in self.list_markdown_skills():
            score = self._match_markdown_score(item, task_text)
            if score <= 0:
                continue
            scored.append({**item, "score": score})
        scored.sort(key=lambda x: int(x.get("score") or 0), reverse=True)
        return scored[: max(1, int(top_k))]

    def suggest_for_task(self, task_text: str, domain: str, top_k: int = 5, include_candidates: bool = True) -> List[Dict[str, Any]]:
        _ = include_candidates
        
        # 1. Get raw suggestions
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            raw_suggestions = [] # Simplify async call inside sync context issues for now
        else:
            raw_suggestions = asyncio.run(self.library.find_for_goal(task_text, domain, top_k))
            
        # 2. Filter by Domain (Atomic Parity)
        from quentin.infra.llm.tool_filter import tool_filter
        refined = tool_filter.filter_tools(raw_suggestions, domain)
        return refined

    def list_sop_prompts(self, domain: str | None = None) -> List[str]:
        sop_dir = self.repo_root / "quentin" / "mutable" / "skills"
        names: List[str] = []
        domain_key = str(domain or "").strip().lower()

        if sop_dir.exists():
            for p in sorted(sop_dir.glob("*.md")):
                stem = p.stem.strip()
                if not stem:
                    continue
                if domain_key and stem.startswith(f"{domain_key}_"):
                    names.append(stem)
                    continue
                names.append(stem)

        for item in self.list_markdown_skills(domain=domain):
            key = str(item.get("skill_id") or item.get("name") or "").strip()
            if key and key not in names:
                names.append(key)
        return names

    def load_sop_prompt(self, name: str) -> str:
        cleaned = str(name or "").strip()
        if not cleaned:
            return ""

        # P2-A: Use pluggable backends first
        for backend in self.backend_registry.list_backends():
            text = backend.load_sop_text(cleaned)
            if text:
                return text

        path = self.repo_root / "quentin" / "mutable" / "skills" / f"{cleaned}.md"
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except Exception:
            pass

        loaded = self.load_markdown_skill(cleaned)
        if loaded:
            body = str(loaded.get("body") or "").strip()
            if body:
                return body

        try:
            return load_sop_skill_md(repo_root=self.repo_root, skill_id=cleaned)
        except Exception:
            return ""

    def suggest_sop_for_task(self, task_text: str, domain: str | None = None) -> str:
        text = (task_text or "").lower()
        matched = self.match_markdown_skills(text, top_k=1)
        if matched:
            return str(matched[0].get("skill_id") or matched[0].get("name") or "")

        available = set(self.list_sop_prompts(domain=domain))
        if ("patch" in text or "fix" in text) and "write_patch" in available:
            return "write_patch"
        if ("review" in text or "audit" in text) and "review_patch" in available:
            return "review_patch"
        return ""

    def load_exec_skill_callable(self, skill_id_or_name: str):
        # P2-A: Use pluggable backends first
        for backend in self.backend_registry.list_backends():
            fn, plugin = backend.load_exec_callable(skill_id_or_name)
            if fn is not None:
                return fn, plugin
                
        # Legacy fallback logic (kept for safety if backends fail or miss something, though backends wrap this logic now)
        plugin = resolve_exec_skill(self.repo_root, skill_id_or_name)
        if plugin is None:
            return None, None
        try:
            fn = load_exec_plugin_callable(plugin=plugin)
        except Exception:
            return None, plugin
        return fn, plugin

    def list_exec_skill_plugins(self, *, domain: str | None = None) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        domain_key = str(domain or "").strip()
        for sk in discover_exec_skill_plugins(self.repo_root):
            if domain_key and sk.domain not in (domain_key, "cross"):
                continue
            items.append(
                {
                    "skill_id": sk.skill_id,
                    "name": sk.name,
                    "domain": sk.domain,
                    "description": sk.description,
                    "tags": list(sk.tags or []),
                    "entrypoint": sk.entrypoint,
                    "plugin_dir": str(sk.dir_path),
                }
            )
        return items

    def mark_implemented(self, *, skill_id: str, module: str, symbol: str, auto_activate: bool = True) -> bool:
        spec = self.registry.get(skill_id)
        if spec is None:
            return False
        try:
            setattr(spec, "implementation_module", module)
            setattr(spec, "implementation_symbol", symbol)
            setattr(spec, "is_implemented", True)
            if auto_activate:
                setattr(spec, "is_active", True)
            self.registry.register(spec)
            return True
        except Exception:
            return False

    def ensure_registry_skill_from_markdown(self, skill_id_or_name: str) -> SkillSpec | None:
        """
        Bridge mode: ensure a markdown-defined skill has a corresponding registry entry.
        """
        md = self.load_markdown_skill(skill_id_or_name)
        if not md:
            return None

        skill_id = str(md.get("skill_id") or "").strip()
        if not skill_id:
            return None

        existing = self.registry.get(skill_id)
        if existing is not None:
            return existing

        name = str(md.get("name") or skill_id).strip() or skill_id
        desc = str(md.get("description") or "").strip()
        domain = str(md.get("frontmatter", {}).get("domain") or "core").strip() or "core"
        tags = []
        triggers = md.get("triggers")
        if isinstance(triggers, list):
            tags = [str(x).strip() for x in triggers if str(x).strip()]

        spec = SkillSpec(
            id=skill_id,
            name=name,
            domain=domain,
            short_description=desc or name,
            detailed_description=desc or name,
            status=SkillStatus.ACTIVE,
            tags=tags,
            notes=f"auto-bridged-from-markdown:{md.get('path')}",
        )
        return self.registry.register(spec)

    def bridge_registry_with_markdown(self, domain: str | None = None) -> List[str]:
        """
        Ensure all discovered markdown skills are represented in JSON registry.
        Returns created skill ids.
        """
        created: List[str] = []
        for item in self.list_markdown_skills(domain=domain):
            skill_id = str(item.get("skill_id") or "").strip()
            if not skill_id or self.registry.get(skill_id) is not None:
                continue
            spec = self.ensure_registry_skill_from_markdown(skill_id)
            if spec is not None:
                created.append(spec.id)
        return created
