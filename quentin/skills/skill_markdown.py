from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SkillMarkdownMeta:
    name: str = ""
    description: str = ""
    requires: List[str] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillMarkdownDocument:
    meta: SkillMarkdownMeta
    body: str
    frontmatter: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillMarkdownDoc:
    skill_id: str
    name: str
    description: str
    triggers: List[str] = field(default_factory=list)
    requires: List[str] = field(default_factory=list)
    body: str = ""
    frontmatter: Dict[str, Any] = field(default_factory=dict)
    path: str = ""


def split_frontmatter(md_text: str) -> Tuple[Optional[str], str]:
    text = md_text or ""
    if not text.lstrip().startswith("---"):
        return None, text
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    end = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end < 0:
        raise ValueError("invalid SKILL.md frontmatter: missing closing '---'")
    frontmatter_text = "\n".join(lines[1:end]).strip()
    body = "\n".join(lines[end + 1 :])
    return frontmatter_text, body


def parse_frontmatter(frontmatter_text: str) -> Dict[str, Any]:
    raw = str(frontmatter_text or "").strip()
    if not raw:
        return {}
    try:
        import yaml
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid SKILL.md frontmatter: yaml unavailable ({exc})") from exc
    try:
        data = yaml.safe_load(raw) or {}
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid SKILL.md frontmatter: yaml parse error ({exc})") from exc
    if not isinstance(data, dict):
        raise ValueError("invalid SKILL.md frontmatter: expected mapping object")
    return data


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            token = str(item or "").strip()
            if token:
                out.append(token)
        return out
    token = str(value or "").strip()
    return [token] if token else []


def parse_skill_markdown(md_text: str) -> SkillMarkdownDocument:
    frontmatter_text, body = split_frontmatter(md_text or "")
    frontmatter = parse_frontmatter(frontmatter_text or "")
    meta = SkillMarkdownMeta(
        name=str(frontmatter.get("name") or "").strip(),
        description=str(frontmatter.get("description") or "").strip(),
        requires=_normalize_list(frontmatter.get("requires")),
        triggers=_normalize_list(frontmatter.get("triggers")),
        extra={k: v for k, v in frontmatter.items() if k not in {"name", "description", "requires", "triggers"}},
    )
    return SkillMarkdownDocument(meta=meta, body=body, frontmatter=frontmatter)


def load_skill_markdown_file(path: Path, default_skill_id: str = "") -> SkillMarkdownDoc:
    text = path.read_text(encoding="utf-8")
    parsed = parse_skill_markdown(text)
    frontmatter = parsed.frontmatter or {}
    skill_id = str(frontmatter.get("id") or default_skill_id or path.parent.name).strip()
    name = parsed.meta.name or skill_id
    description = parsed.meta.description
    return SkillMarkdownDoc(
        skill_id=skill_id,
        name=name,
        description=description,
        triggers=list(parsed.meta.triggers or []),
        requires=list(parsed.meta.requires or []),
        body=parsed.body,
        frontmatter=dict(frontmatter),
        path=str(path),
    )
