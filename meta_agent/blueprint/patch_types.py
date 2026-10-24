# meta_agent/blueprint/patch_types.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import datetime as dt
import uuid


@dataclass
class BlueprintPatch:
    """
    一次蓝皮书改动提案（Text-level Patch）。
    """
    id: str
    created_at: str
    source: str                    # "gap_quality" | "meta_research" | "manual"
    author: str                    # "llm_codex" | "llm_gemini" | "human"
    target_section: str            # e.g., "2.1 Memory Fabric"
    change_type: str               # "rewrite_section" | "append_section" | "insert_before" | "insert_after"
    old_excerpt: Optional[str] = None
    new_content: str = ""
    rationale: str = ""
    risk_level: str = "medium"      # "low" | "medium" | "high"
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: str = "proposed"       # "proposed" | "approved" | "rejected" | "applied"


def make_blueprint_patch_id() -> str:
    today = dt.date.today().strftime("%Y%m%d")
    short = uuid.uuid4().hex[:6].upper()
    return f"BP-{today}-{short}"
