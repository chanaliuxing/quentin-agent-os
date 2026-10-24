from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from quentin.cognitive.prompt_layers import build_layered_system_prompt
from quentin.cognitive.phase_payloads import normalize_phase
from quentin.infra.perception.capabilities import CapabilityDiscovery
from quentin.runtime.silent_protocol import SILENT_REPLY_TOKEN

PromptMode = str  # "full" | "minimal" | "none"

@dataclass
class RuntimeInfo:
    agent_id: str = "quentin"
    workspace: str = "."
    os_name: str = "unknown"
    model: str = "unknown"
    budget_remaining: Optional[str] = None
    extras: Dict[str, str] = field(default_factory=dict)
    thinking: str = "off"

def _clean(text: Optional[str]) -> str:
    return str(text or "").strip()

def _join_non_empty(lines: Iterable[str]) -> str:
    return "\n".join([line for line in lines if _clean(line)]).strip()

def _format_runtime(info: RuntimeInfo) -> str:
    lines: List[str] = [
        f"agent={info.agent_id}",
        f"workspace={info.workspace}",
        f"os={info.os_name}",
        f"model={info.model}",
    ]
    if _clean(info.budget_remaining):
        lines.append(f"budget={info.budget_remaining}")
    
    lines.append(f"thinking={info.thinking}")
    
    for key, value in (info.extras or {}).items():
        k = _clean(key)
        v = _clean(value)
        if k and v:
            lines.append(f"{k}={v}")
    return "Runtime: " + " | ".join(lines)

def _format_tool_summaries(enabled_tools: Optional[Dict[str, str]]) -> str:
    if not enabled_tools:
        return ""
    
    lines = ["Tools (short summaries):"]
    for name in sorted(enabled_tools.keys()):
        summary = _clean(enabled_tools.get(name))
        line = f"- {name}: {summary}"
        lines.append(line)
    return "\n".join(lines)

def _load_foundation(mode: str) -> Dict[str, Any]:
    """Loads mode-specific foundation from YAML."""
    path = Path("config/prompts/foundation.yaml")
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get(mode, {})
    except:
        return {}

def build_system_prompt(
    *,
    mode: PromptMode = "full",
    identity: Optional[str] = None,
    safety_rules: Optional[Iterable[str]] = None,
    enabled_tools: Optional[Dict[str, str]] = None,
    skill_context: str = "",
    memory_context: str = "",
    project_context: str = "",
    runtime_info: Optional[RuntimeInfo] = None,
    hints: Optional[Iterable[str]] = None,
    phase_payload: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build a high-autonomy system prompt with MAXIMUM OpenClaw parity.
    """
    normalized_mode = _clean(mode).lower() or "full"
    
    if normalized_mode == "none":
        return "You are a personal assistant running inside Quentin OS."

    foundation = _load_foundation(normalized_mode)
    is_minimal = normalized_mode == "minimal"
    normalized_phase = normalize_phase((phase_payload or {}).get("phase"))

    phase_templates: Dict[str, Dict[str, str]] = {
        "planning": {
            "identity": "You are Quentin PLANNING STATE machine. Produce safe, concrete, verifiable plans.",
            "directive": (
                "## Planning State Template\n"
                "- Focus: decomposition, environment verification, risk minimization.\n"
                "- Before risky actions, require discovery prechecks.\n"
                "- Avoid speculative assumptions; use observable state."
            ),
        },
        "executing": {
            "identity": "You are Quentin EXECUTING STATE machine. Execute deterministically using real tools.",
            "directive": (
                "## Executing State Template\n"
                "- Focus: precise tool invocation and physical-state updates.\n"
                "- Do not claim completion without tool evidence.\n"
                "- Stop repeated calls that do not change state."
            ),
        },
        "reflecting": {
            "identity": "You are Quentin REFLECTING STATE machine. Diagnose root cause and prescribe corrections.",
            "directive": (
                "## Reflecting State Template\n"
                "- Focus: failure attribution and correction strategy.\n"
                "- Distinguish tool failure from strategy/path failure.\n"
                "- Output concrete next-step corrections."
            ),
        },
    }
    phase_template = phase_templates.get(normalized_phase, phase_templates["planning"])

    # 0. Environmental Perception
    caps = CapabilityDiscovery.get_active_capabilities()
    perception_hints = []
    if caps.get("mobile"): perception_hints.append("PHYSICAL_NODE: Android device detected.")
    if caps.get("browser"): perception_hints.append("BROWSER_NODE: Automation engine ready.")
    if caps.get("sandbox"): perception_hints.append("RUNTIME_SHIELD: Secure sandbox active.")

    # 1. Identity
    final_identity = identity or phase_template.get("identity") or foundation.get("identity", "You are a personal assistant.")
    
    # 2. Safety & Thought Protocol
    all_safety = list(foundation.get("safety", []))
    if safety_rules:
        all_safety.extend(list(safety_rules))
    
    thought_text = ""
    if not is_minimal:
        thought_text = "## Reasoning Protocol\n" + foundation.get("thought_protocol", "")
        
        memory_guidance = foundation.get("memory_guidance")
        if memory_guidance and enabled_tools and ("memory_search" in enabled_tools or "memory_get" in enabled_tools):
            thought_text += f"\n## Memory Recall\n{memory_guidance}\n"

    style_guidance = foundation.get("style", [])
    style_text = ""
    if style_guidance:
        style_text = "## Tool Call Style\n" + "\n".join([f"- {s}" for s in style_guidance])

    safety_text = _join_non_empty([f"- {s}" for s in all_safety])
    if safety_text:
        safety_text = "Safety:\n" + safety_text
    
    # 3. Runtime & Events
    runtime_text = _format_runtime(runtime_info or RuntimeInfo())
    
    # P5: Surgery Forty-four - Dynamic Instruction Boosting (OpenClaw Parity)
    failure_count = int(getattr(runtime_info, "extras", {}).get("failure_count", 0) if runtime_info else 0)
    last_error = getattr(runtime_info, "extras", {}).get("last_error") if runtime_info else None
    try:
        from quentin.cognitive.perception.instruction_booster import InstructionBooster

        booster_text = InstructionBooster.get_boosted_instruction(failure_count, last_error)
    except Exception:
        booster_text = ""
    if booster_text:
        runtime_text += booster_text
    
    from quentin.runtime.system_events import system_events
    event_block = system_events.format_for_prompt()
    if event_block:
        runtime_text += "\n\n## System Events\n" + event_block

    if perception_hints:
        runtime_text += "\n" + "\n".join(perception_hints)

    # 4. Assembling Layers
    tools_text = _format_tool_summaries(enabled_tools)
    skill_text = _clean(skill_context)
    memory_text = _clean(memory_context)
    project_text = _clean(project_context)

    layered_project_parts: List[str] = []
    
    # P1: Runtime Environment Injection (Hardening against fake imports)
    runtime_env = foundation.get("runtime_environment")
    if runtime_env:
        layered_project_parts.append(runtime_env)

    if not is_minimal:
        if tools_text:
            layered_project_parts.append(tools_text)
        
        # New: Reply Tags
        tags = foundation.get("reply_tags")
        if tags: layered_project_parts.append(tags)

        # New: Sandbox Guardrails
        sandbox = foundation.get("sandbox_guardrails")
        if sandbox: layered_project_parts.append(sandbox)

        if skill_text:
            layered_project_parts.append("Skills:\n" + skill_text)
        
        # New: Skills Lazy Loading Protocol
        skills_protocol = foundation.get("skills_protocol")
        if skills_protocol:
            layered_project_parts.append(skills_protocol)

        if memory_text:
            layered_project_parts.append("Memory:\n" + memory_text)
        
        # OpenClaw Full Parity: Silent Replies & Heartbeats
        silent_guidance = foundation.get("silent_replies")
        if silent_guidance:
            layered_project_parts.append(f"## Silent Replies\n{silent_guidance}")

        heartbeat_guidance = foundation.get("heartbeats")
        if heartbeat_guidance:
            layered_project_parts.append(f"## Heartbeats\n{heartbeat_guidance}")
        
        # New: Diagnostics & Tool Results
        tr_guidance = foundation.get("tool_result_guidance")
        if tr_guidance:
            layered_project_parts.append(tr_guidance)
        
        # New: Docs & Help
        docs_help = foundation.get("docs_and_help")
        if docs_help: layered_project_parts.append(docs_help)

        # New: CLI Reference
        cli_ref = foundation.get("cli_reference")
        if cli_ref:
            layered_project_parts.append(cli_ref)

    if project_text:
        layered_project_parts.append("## Project Context\n" + project_text)

    phase_payload_text = ""
    if phase_payload:
        phase_payload_text = f"Phase Payload: {phase_payload}"
    phase_directive = phase_template.get("directive") or ""
    if phase_directive:
        layered_project_parts.append(phase_directive)
    if phase_payload_text:
        layered_project_parts.append(phase_payload_text)

    layered_project_parts.append(runtime_text)
    merged_project_context = "\n\n".join([p for p in layered_project_parts if _clean(p)])

    return build_layered_system_prompt(
        base_system=_clean(final_identity),
        soul="",
        skill=_join_non_empty([thought_text, safety_text, style_text]),
        project_context=merged_project_context,
        hints=hints,
    )
