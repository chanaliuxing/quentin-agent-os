from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from quentin.skills.skill_markdown import parse_frontmatter


@dataclass
class SopSkill:
    skill_id: str
    name: str
    description: str
    triggers: List[str]
    requires: List[str]
    dir_path: Path
    skill_md_path: Path
    meta: Dict[str, Any]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "on")

def _skill_md_enabled() -> bool:
    raw = os.getenv("QUENTIN_SKILL_MD_ENABLED")
    if raw is not None:
        return _env_bool("QUENTIN_SKILL_MD_ENABLED", False)
    legacy = os.getenv("QUENTIN_SOP_SKILLS_ENABLED")
    if legacy is not None:
        return _env_bool("QUENTIN_SOP_SKILLS_ENABLED", False)
    return False


def resolve_sop_dirs(repo_root: str | Path) -> List[Path]:
    root = Path(repo_root).resolve()
    override = (os.getenv("QUENTIN_SOP_SKILLS_DIRS") or "").strip()
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


def _read_frontmatter_block(path: Path) -> str:
    # Read only the frontmatter block; body stays unloaded until explicit load.
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return ""
    if not lines or lines[0].strip() != "---":
        return ""
    end = -1
    for idx in range(1, min(len(lines), 200)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end < 0:
        return ""
    return "\n".join(lines[1:end]).strip()


def _normalize_list(value: Any) -> List[str]:
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            token = str(item or "").strip()
            if token:
                out.append(token)
        return out
    token = str(value or "").strip()
    return [token] if token else []


def discover_sop_skills(repo_root: str | Path) -> List[SopSkill]:
    if not _skill_md_enabled():
        return []
    out: List[SopSkill] = []
    for base in resolve_sop_dirs(repo_root):
        if not base.exists():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            md = child / "SKILL.md"
            if not md.exists():
                continue
            frontmatter = _read_frontmatter_block(md)
            try:
                fm = parse_frontmatter(frontmatter)
            except Exception:
                fm = {}
            skill_id = str(fm.get("id") or child.name).strip() or child.name
            name = str(fm.get("name") or skill_id).strip() or skill_id
            desc = str(fm.get("description") or "").strip()
            triggers = _normalize_list(fm.get("triggers"))
            requires = _normalize_list(fm.get("requires"))
            out.append(
                SopSkill(
                    skill_id=skill_id,
                    name=name,
                    description=desc,
                    triggers=triggers,
                    requires=requires,
                    dir_path=child,
                    skill_md_path=md,
                    meta=fm if isinstance(fm, dict) else {},
                )
            )
    return out


def load_sop_skill_md(*, repo_root: str | Path, skill_id: str) -> str:
    sid = str(skill_id or "").strip()
    if not sid:
        return ""
    for skill in discover_sop_skills(repo_root):
        if skill.skill_id == sid or skill.name == sid:
            try:
                return skill.skill_md_path.read_text(encoding="utf-8")
            except Exception:
                return ""
    return ""
