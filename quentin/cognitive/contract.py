from __future__ import annotations

import re
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path

@dataclass
class PhysicalAnchor:
    """
    Defines a physical state that must be reached for the requirement to be met.
    """
    kind: str  # file_content, file_exists, port_open, shell_exit_zero
    target: str
    expected_value: Optional[Any] = None
    initial_value: Optional[Any] = None

@dataclass
class CognitiveContract:
    """
    P5: Ported from OpenClaw's MsgContext and System Contract.
    Enhanced with Physical Success Anchors.
    """
    task_id: str
    raw_input: str
    domain: str
    intent: str
    constraints: List[str] = field(default_factory=list)
    perceived_evidence: Dict[str, Any] = field(default_factory=dict)
    physical_anchors: List[PhysicalAnchor] = field(default_factory=list)
    safety_level: str = "standard"
    is_ambiguous: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_prompt_block(self) -> str:
        constraints_str = "\n".join([f"- {c}" for c in self.constraints])
        anchors_str = "\n".join([f"- [{a.kind}] {a.target}" for a in self.physical_anchors])
        return f"""
<requirement_contract>
INTENT: {self.intent}
DOMAIN: {self.domain}
SAFETY_LEVEL: {self.safety_level}
AMBIGUOUS: {self.is_ambiguous}

PHYSICAL_SUCCESS_ANCHORS:
{anchors_str}

PRIMARY_CONSTRAINTS:
{constraints_str}
</requirement_contract>
"""

class RequirementContractor:
    """
    The 'First Second' processor.
    Analyzes the task to build a CognitiveContract.
    """
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def build_contract(self, task_input: str, task_id: str, perception_data: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> CognitiveContract:
        md = metadata or {}
        
        # 1. Infer Domain & Intent
        domain, intent = self._classify_intent(task_input)
        
        # 2. Extract Physical Anchors (Success Definitions)
        anchors = self._extract_anchors(task_input, perception_data)
        
        # 3. Detect Ambiguity
        is_ambiguous = len(task_input.split()) < 4 and not anchors
        
        # 4. Extract Implicit Constraints
        constraints = self._extract_constraints(task_input, perception_data)
        
        # P5: Surgery Fifteen - Sub-agent Context Isolation
        if md.get("is_subagent"):
            parent_id = md.get("spawned_by", "unknown")
            constraints.append(f"MISSION CONTEXT: You are a sub-agent spawned by {parent_id}.")
            constraints.append("ISOLATION: Focus ONLY on the provided task. Do not attempt to manage parent sessions.")
            constraints.append("REPORTING: Your final_output will be sent back to your parent agent as a tool result.")

        # 5. Determine Safety Level
        safety = "standard"
        if any(word in task_input.lower() for word in ["delete", "rm ", "format", "dangerous"]):
            safety = "high"

        return CognitiveContract(
            task_id=task_id,
            raw_input=task_input,
            domain=domain,
            intent=intent,
            constraints=constraints,
            perceived_evidence=perception_data,
            physical_anchors=anchors,
            safety_level=safety,
            is_ambiguous=is_ambiguous
        )

    def _extract_anchors(self, text: str, perception: Dict[str, Any]) -> List[PhysicalAnchor]:
        anchors = []
        
        # Heuristic: Find paths mentioned in text or perception
        mentioned_files = []
        # From perception
        for f in perception.get("files", []):
            mentioned_files.append(f["path"])
            
        # Regex for paths in text
        matches = re.findall(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]*", text)
        mentioned_files.extend(matches)
        
        # Unique and clean
        mentioned_files = list(set([f.strip("./") for f in mentioned_files if f.strip()]))
        
        t = text.lower()
        for f in mentioned_files:
            if any(k in t for k in ["fix", "edit", "update", "write", "add"]):
                anchors.append(PhysicalAnchor(kind="file_content", target=f))
            elif any(k in t for k in ["check", "read", "exists"]):
                anchors.append(PhysicalAnchor(kind="file_exists", target=f))
                
        # Command anchors
        if "run" in t or "execute" in t:
            anchors.append(PhysicalAnchor(kind="shell_exit_zero", target="command_execution"))
            
        return anchors

    def _classify_intent(self, text: str) -> tuple[str, str]:
        t = text.lower()
        if any(k in t for k in ["fix", "bug", "error", "issue", "fails"]):
            return "coding", "bug_fix"
        if any(k in t for k in ["add", "implement", "create", "feature"]):
            return "coding", "feature_dev"
        if any(k in t for k in ["analyze", "search", "find", "research", "what is"]):
            return "research", "analysis"
        if any(k in t for k in ["clean", "update", "maintenance", "refactor"]):
            return "maintenance", "refactor"
        return "general", "task_execution"

    def _extract_constraints(self, text: str, perception: Dict[str, Any]) -> List[str]:
        constraints = ["Do not hallucinate facts.", "Maintain existing code style."]
        
        # Environmental constraints
        files = perception.get("files", [])
        if any(f["path"].endswith(".py") for f in files):
            constraints.append("Language constraint: Use Python 3.10+ syntax.")
            constraints.append("Adhere to PEP8 formatting.")
        
        if any(f["path"].endswith(".js") or f["path"].endswith(".ts") for f in files):
            constraints.append("Language constraint: Use TypeScript/ESNext.")
            
        # P5: Coding tool preference
        if any(k in text.lower() for k in ["fix", "implement", "refactor", "add feature"]):
            primary = str(os.getenv("QUENTIN_CODING_TOOL_PRIMARY", "gemini.code") or "").strip()
            fallback_raw = str(os.getenv("QUENTIN_CODING_TOOL_FALLBACKS", "coder.generate") or "")
            fallbacks = [x.strip() for x in fallback_raw.split(",") if x.strip()]
            tool_names: List[str] = []
            for x in [primary, *fallbacks]:
                if x and x not in tool_names:
                    tool_names.append(x)
            tool_hint = "/".join(tool_names[:3]) if tool_names else "configured coding tools"
            constraints.append(
                f"Tooling: For complex code modification, prefer using {tool_hint} "
                "to ensure high-quality, architecturally-sound patches."
            )

        # Task-specific constraints
        if "test" in text.lower() or "verify" in text.lower():
            constraints.append("Verification: Ensure all new code has matching unit tests.")
            
        return constraints
