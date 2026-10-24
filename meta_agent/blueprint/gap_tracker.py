# meta_agent/blueprint/gap_tracker.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any

from meta_agent.blueprint.model import BlueprintDocument, BlueprintClause

class GapType(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    IMPLEMENTED_NO_TESTS = "implemented_no_tests"
    IMPLEMENTED_BUT_UNSTABLE = "implemented_but_unstable"

@dataclass
class BlueprintGap:
    clause_id: str
    gap_type: GapType
    details: str = ""
    implementation_refs: List[str] = field(default_factory=list)
    
class BlueprintGapTrackerV2:
    def __init__(self, blueprint: BlueprintDocument):
        self.blueprint = blueprint

    def analyze(self) -> List[BlueprintGap]:
        """
        Analyzes the blueprint to find gaps based on quality and coverage.
        V2 implementation.
        """
        gaps: List[BlueprintGap] = []
        
        for section in self.blueprint.sections:
            for clause in section.clauses:
                implementation_refs = self._find_implementation_refs(clause)

                if not implementation_refs:
                    gaps.append(BlueprintGap(
                        clause_id=clause.id,
                        gap_type=GapType.NOT_IMPLEMENTED,
                        details=f"No implementation references found for clause '{clause.title}'.",
                    ))
                    continue

                # 2. Check for test coverage
                has_tests = self._check_test_coverage(implementation_refs)
                if not has_tests:
                     gaps.append(BlueprintGap(
                        clause_id=clause.id,
                        gap_type=GapType.IMPLEMENTED_NO_TESTS,
                        details=f"Implementation found for '{clause.title}', but no corresponding tests were detected.",
                        implementation_refs=implementation_refs,
                    ))

                # 3. Check for stability from recent metrics
                is_unstable = self._check_stability(clause)
                if is_unstable:
                     gaps.append(BlueprintGap(
                        clause_id=clause.id,
                        gap_type=GapType.IMPLEMENTED_BUT_UNSTABLE,
                        details=f"Clause '{clause.title}' implementation may be unstable based on recent error reports.",
                        implementation_refs=implementation_refs,
                    ))

        return gaps
        
    def _find_implementation_refs(self, clause: BlueprintClause) -> List[str]:
        """
        Heuristic implementation search:
        - Search for `clause.id` in `meta_agent/**/*.py` and `quentin/**/*.py`
        - Return relative file paths of matches (deduplicated)

        This is intentionally conservative and bounded to keep local runs fast.
        """
        from pathlib import Path

        needle = str(clause.id or "").strip()
        if not needle:
            return []

        roots = [Path("meta_agent"), Path("quentin")]
        matches: List[str] = []
        max_files = 2500
        max_matches = 30
        scanned = 0

        for root in roots:
            if not root.exists():
                continue
            for p in root.rglob("*.py"):
                scanned += 1
                if scanned > max_files or len(matches) >= max_matches:
                    break
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if needle in text:
                    matches.append(str(p))
            if scanned > max_files or len(matches) >= max_matches:
                break

        # Deduplicate while preserving order.
        seen = set()
        out: List[str] = []
        for m in matches:
            if m in seen:
                continue
            seen.add(m)
            out.append(m)
        return out

    def _check_test_coverage(self, refs: List[str]) -> bool:
        """
        Heuristic test coverage check:
        - If any `tests/**/test_*.py` mentions an implementation ref path, treat as covered.
        """
        from pathlib import Path

        test_root = Path("tests")
        if not test_root.exists():
            return False
        needles = [Path(r).name for r in (refs or []) if r]
        if not needles:
            return False

        for p in test_root.rglob("test_*.py"):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for n in needles:
                if n and n in text:
                    return True
        return False

    def _check_stability(self, clause: BlueprintClause) -> bool:
        """
        Minimal stability signal:
        - If clause status is IMPLEMENTED, assume stable.
        - Otherwise return False (unknown / not enough signal).
        """
        try:
            return str(getattr(clause, "status", "")).lower() not in ("implemented", "deprecated")
        except Exception:
            return False
