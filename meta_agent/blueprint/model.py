# meta_agent/blueprint/model.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any


class BlueprintClauseStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"
    DEPRECATED = "deprecated"


class BlueprintClauseCategory(str, Enum):
    ARCHITECTURE = "architecture"
    SAFETY = "safety"
    RESEARCH = "research"
    DOMAIN_DESKTOP = "domain-desktop"
    DOMAIN_LEGAL = "domain-legal"
    OTHER = "other"


@dataclass
class BlueprintClause:
    """
    蓝皮书中的一个具体条款。
    """
    id: str
    title: str
    category: BlueprintClauseCategory
    priority: int = 3
    status: BlueprintClauseStatus = BlueprintClauseStatus.PLANNED
    depends_on: List[str] = field(default_factory=list)
    rationale: str = ""
    acceptance_criteria: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category.value,
            "priority": self.priority,
            "status": self.status.value,
            "depends_on": self.depends_on,
            "rationale": self.rationale,
            "acceptance_criteria": self.acceptance_criteria,
        }


@dataclass
class BlueprintSection:
    """
    蓝皮书中的一个章节，包含一组条款。
    """
    title: str
    clauses: List[BlueprintClause] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "clauses": [c.to_dict() for c in self.clauses],
        }


@dataclass
class BlueprintDocument:
    """
    完整的、结构化的蓝皮书文档。
    """
    version: str
    sections: List[BlueprintSection] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "sections": [s.to_dict() for s in self.sections],
        }
