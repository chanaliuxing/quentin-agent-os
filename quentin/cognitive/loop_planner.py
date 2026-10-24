from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import logging
import os
import platform
import re
from pathlib import Path

from quentin.council.manager import CouncilQuestion
from quentin.cognitive.prompt_factory import build_system_prompt, RuntimeInfo
from quentin.cognitive.phase_payloads import build_phase_payload

logger = logging.getLogger(__name__)


def _infer_expected_tool_from_text(text: str) -> str:
    t = str(text or "").strip().lower()
    if not t:
        return ""
    explicit = (
        "fs.read_file",
        "fs.write_file",
        "fs.search_replace",
        "shell.run_command",
        "ls",
        "mkdir",
        "cat",
        "grep",
        "find",
    )
    for tool in explicit:
        if tool in t:
            return tool
    token_map = {
        "read_file": "fs.read_file",
        "write_file": "fs.write_file",
        "search_replace": "fs.search_replace",
        "list directory": "ls",
        "create directory": "mkdir",
    }
    for token, tool in token_map.items():
        if token in t:
            return tool
    return ""


def _fallback_families_for_expected_tool(expected_tool: str) -> List[str]:
    tool = str(expected_tool or "").strip().lower()
    if not tool:
        return []
    if tool.startswith("fs.") or tool in {"ls", "cat", "mkdir", "grep", "find"}:
        return ["filesystem", "shell"]
    if tool.startswith("shell."):
        return ["shell", "filesystem"]
    if tool.startswith("browser.") or tool.startswith("web_search."):
        return ["browser"]
    return ["generic"]


def _normalize_step_tool_intent(step: Dict[str, Any]) -> Dict[str, Any]:
    src = step.get("tool_intent") if isinstance(step.get("tool_intent"), dict) else {}
    expected = str(src.get("expected_tool") or "").strip().lower()
    if not expected:
        expected = _infer_expected_tool_from_text(str(step.get("description") or ""))
    if not expected:
        expected = _infer_expected_tool_from_text(str(step.get("notes") or ""))
    if not expected:
        expected = str(step.get("tool") or step.get("name") or "").strip().lower()
    fallback = src.get("allowed_fallback_families")
    fallback_list: List[str] = []
    if isinstance(fallback, list):
        fallback_list = [str(x).strip().lower() for x in fallback if str(x).strip()]
    if not fallback_list:
        fallback_list = _fallback_families_for_expected_tool(expected)
    return {
        "expected_tool": expected,
        "allowed_fallback_families": fallback_list,
        "why": str(src.get("why") or "align_step_and_execution").strip(),
    }


def _extract_explicit_paths_from_task_text(task_text: str) -> List[str]:
    text = str(task_text or "")
    candidates: List[str] = []
    patterns = [
        r"`([^`\n]+)`",
        r"'([^'\n]+)'",
        r"\"([^\"\n]+)\"",
        r"(?<![\w/.-])(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            value = str(match or "").strip().strip("/")
            if value:
                candidates.append(value)
    out: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _maybe_build_deterministic_report_plan(*, repo_root: Path, task_text: str) -> Optional[Dict[str, Any]]:
    """
    Detect a narrow but high-value class of tasks:
    inspect a set of explicit files, then create a report file with exact lines.
    This lets canary/report tasks bypass slow local-planner LLM calls entirely.
    """
    text = str(task_text or "").strip()
    lowered = text.lower()
    if not text:
        return None
    if "create " not in lowered or "exactly" not in lowered or "line" not in lowered:
        return None

    explicit_paths = _extract_explicit_paths_from_task_text(text)
    if len(explicit_paths) < 2:
        return None
    report_path = explicit_paths[-1]
    source_paths = explicit_paths[:-1]
    if not source_paths or not report_path:
        return None

    line_match = re.search(r"exactly\s+\w+\s+lines?\s*:\s*(.+)$", text, flags=re.IGNORECASE | re.DOTALL)
    if not line_match:
        return None
    raw_lines = [seg.strip() for seg in line_match.group(1).split(",")]
    template_lines = [seg for seg in raw_lines if seg]
    if not template_lines:
        return None

    resolved_sources: List[str] = []
    for rel in source_paths:
        p = (repo_root / rel).resolve()
        try:
            p.relative_to(repo_root)
        except Exception:
            return None
        resolved_sources.append(str(p.relative_to(repo_root)))
    target = (repo_root / report_path).resolve()
    try:
        target.relative_to(repo_root)
    except Exception:
        return None
    rel_target = str(target.relative_to(repo_root))

    # Expand "...=yes or no" placeholders using actual repo state.
    final_lines: List[str] = []
    for line in template_lines:
        # Allow optional trailing punctuation so prompts ending with "yes or no."
        # are still normalized to strict yes/no values.
        match = re.match(
            r"^(?P<prefix>.+?)=\s*yes\s+or\s+no(?:[\s\.\!\?。！？]*)$",
            line,
            flags=re.IGNORECASE,
        )
        if match:
            prefix = str(match.group("prefix") or "").strip()
            normalized_prefix = prefix.lower().replace(" ", "_")
            normalized_prefix = re.sub(r"_present$", "", normalized_prefix)
            status = "no"
            for source in resolved_sources:
                stem = Path(source).stem.lower().replace(" ", "_")
                name = Path(source).name.lower().replace(" ", "_")
                if normalized_prefix in {stem, name}:
                    status = "yes" if (repo_root / source).exists() else "no"
                    break
            final_lines.append(f"{prefix}={status}")
        else:
            final_lines.append(line)

    encoded_content = json.dumps("\n".join(final_lines), ensure_ascii=False)
    steps: List[Dict[str, Any]] = []
    for idx, source in enumerate(resolved_sources, start=1):
        steps.append(
            {
                "step_id": f"s{idx}",
                "description": f"Read the target file `{source}` using fs.read_file.",
                "skill_id": None,
                "notes": "deterministic_report_read",
                "tool_intent": {
                    "expected_tool": "fs.read_file",
                    "allowed_fallback_families": ["filesystem", "shell"],
                    "why": "ground report against explicit inputs",
                },
            }
        )
    steps.append(
        {
            "step_id": f"s{len(steps) + 1}",
            "description": (
                f"Write the exact report file `{rel_target}` using fs.write_file with JSON content {encoded_content}."
            ),
            "skill_id": None,
            "notes": "deterministic_report_write",
            "tool_intent": {
                "expected_tool": "fs.write_file",
                "allowed_fallback_families": ["filesystem", "shell"],
                "why": "materialize deterministic report",
            },
        }
    )
    return {
        "steps": steps,
        "used_skills": [],
        "raw_output": json.dumps({"source": "deterministic_report_plan", "steps": steps}, ensure_ascii=False),
    }


def _resolve_correction_intensity_from_context(context: Dict[str, Any]) -> str:
    eval_data = context.get("last_attempt_evaluation") if isinstance(context, dict) else {}
    if isinstance(eval_data, dict):
        val = str(eval_data.get("correction_intensity") or "").strip().lower()
        if val in {"low", "medium", "high", "critical"}:
            return val
    return "medium"


def _build_planner_phase_system_prompt(
    loop: Any,
    *,
    goal: Any,
    skill_suggestions: List[Dict[str, Any]],
    context: Dict[str, Any],
    safety_rules: Optional[List[str]] = None,
) -> str:
    correction_intensity = _resolve_correction_intensity_from_context(context or {})
    lifecycle = (context or {}).get("planner_lifecycle_payload") if isinstance((context or {}).get("planner_lifecycle_payload"), dict) else {}
    attempt_stage = str(lifecycle.get("stage") or "initial").strip().lower() or "initial"
    stage_directives = [str(x) for x in (lifecycle.get("directives") or []) if str(x).strip()]
    strategy_patch = (context or {}).get("planning_strategy_patch") if isinstance((context or {}).get("planning_strategy_patch"), dict) else {}
    strategy_directives = [str(x) for x in (strategy_patch.get("directives") or []) if str(x).strip()]
    strategy_category = str(strategy_patch.get("category") or "").strip()
    payload_variant = (context or {}).get("planner_payload_variant") if isinstance((context or {}).get("planner_payload_variant"), dict) else {}
    variant_directives = [str(x) for x in (payload_variant.get("directives") or []) if str(x).strip()]
    variant_id = str(payload_variant.get("variant_id") or "").strip()
    phase_payload = build_phase_payload(
        phase="planning",
        attempt_stage=attempt_stage,
        correction_intensity=correction_intensity,
        reason="planner_entry",
        directives=stage_directives,
    ).to_dict()
    enabled_tools: Dict[str, str] = {}
    raw_summaries = (context or {}).get("tool_summaries")
    if isinstance(raw_summaries, dict):
        for name, summary in raw_summaries.items():
            key = str(name or "").strip()
            if not key:
                continue
            enabled_tools[key] = str(summary or "").strip() or "tool available"
    return build_system_prompt(
        mode="minimal" if bool((context or {}).get("is_subagent")) else "full",
        identity="You are a planning agent in Quentin cognitive loop.",
        safety_rules=safety_rules
        or [
            "You have no independent goals.",
            "Prefer small, executable, low-risk steps.",
            "Return schema-compliant JSON under answer.",
        ],
        enabled_tools=enabled_tools,
        skill_context="Use known skills when clearly helpful.",
        memory_context=((str((context or {}).get("historical_attempts") or "") + "\n\n" + str((context or {}).get("system_event_prompt") or "")).strip()),
        project_context=str((context or {}).get("current_environment_tree") or ""),
        runtime_info=RuntimeInfo(
            agent_id="quentin-cognitive-loop",
            workspace=str(loop.repo_root),
            os_name=platform.system().lower() or "unknown",
            model="planner-council",
            budget_remaining=str((goal.metadata or {}).get("budget_remaining") or ""),
            extras={"goal_id": str(goal.goal_id)},
        ),
        hints=[
            "Prefer concrete steps and explicit success checks.",
            "Do not include prose outside the expected JSON answer.",
            f"Planner lifecycle stage: {attempt_stage}",
            *stage_directives[:3],
            *(["Failure strategy patch category: " + strategy_category] if strategy_category else []),
            *strategy_directives[:2],
            *(["Planner payload variant: " + variant_id] if variant_id else []),
            *variant_directives[:2],
        ],
        phase_payload=phase_payload,
    )


def run_planner(loop: Any, goal: Any, context: Dict[str, Any]) -> Dict[str, Any]:
    domain = goal.domain or "core"
    task_text = goal.description or goal.title or ""
    if not task_text:
        task_text = f"Goal {goal.goal_id}"

    deterministic = _maybe_build_deterministic_report_plan(repo_root=Path(loop.repo_root), task_text=task_text)
    if isinstance(deterministic, dict):
        return {
            "goal_id": goal.goal_id,
            "raw_output": str(deterministic.get("raw_output") or ""),
            "steps": list(deterministic.get("steps") or []),
            "used_skills": list(deterministic.get("used_skills") or []),
        }

    skill_suggestions: List[Dict[str, Any]] = []
    available_sops: List[str] = []
    suggested_sop: str = ""
    available_exec_skills: List[Dict[str, Any]] = []
    graph_facts: str = ""
    try:
        if loop.skill_manager is not None:
            skill_suggestions = loop.skill_manager.suggest_for_task(
                task_text=task_text,
                domain=domain,
                top_k=5,
                include_candidates=True,
            )
            available_sops = loop.skill_manager.list_sop_prompts(domain=domain)
            suggested_sop = loop.skill_manager.suggest_sop_for_task(task_text=task_text, domain=domain)
            available_exec_skills = loop.skill_manager.list_exec_skill_plugins(domain=domain)

        if hasattr(loop, "knowledge_graph") and loop.knowledge_graph:
            entities = [t for t in re.findall(r"\\b[A-Z][a-z]{3,}\\b", task_text)]
            if entities:
                graph_facts = loop.knowledge_graph.get_context_text(entities)
    except Exception:
        logger.exception("CognitiveLoop._run_planner: failed to get skill/graph suggestions")

    importance = (goal.metadata or {}).get("importance", "normal")
    plan_schema_text = (
        "{\n"
        "  \"steps\": [\n"
        "    {\n"
        "      \"step_id\": \"s1\",\n"
        "      \"description\": \"...\",\n"
        "      \"skill_id\": \"...\" | null,\n"
        "      \"notes\": \"...\",\n"
        "      \"tool_intent\": {\n"
        "        \"expected_tool\": \"fs.read_file|fs.search_replace|shell.run_command|ls|mkdir|...\",\n"
        "        \"allowed_fallback_families\": [\"filesystem\", \"shell\", \"browser\"],\n"
        "        \"why\": \"one short reason\"\n"
        "      }\n"
        "    },\n"
        "    ...\n"
        "  ]\n"
        "}\n"
    )
    planner_prompt = loop._build_planner_question_prompt(
        goal=goal,
        task_text=task_text,
        plan_schema_text=plan_schema_text,
        skill_suggestions=skill_suggestions,
        context=context or {},
    )
    if graph_facts:
        planner_prompt += f"\n\n{graph_facts}"
    planning_correction_intensity = _resolve_correction_intensity_from_context(context or {})
    lifecycle = (context or {}).get("planner_lifecycle_payload") if isinstance((context or {}).get("planner_lifecycle_payload"), dict) else {}
    attempt_stage = str(lifecycle.get("stage") or "initial").strip().lower() or "initial"
    stage_directives = [str(x) for x in (lifecycle.get("directives") or []) if str(x).strip()]
    planning_phase_payload = build_phase_payload(
        phase="planning",
        attempt_stage=attempt_stage,
        correction_intensity=planning_correction_intensity,
        reason="planner_council_question",
        directives=stage_directives,
    ).to_dict()
    task_obj = (context or {}).get("task") if isinstance(context, dict) else None
    task_meta = getattr(task_obj, "metadata", {}) if task_obj is not None else {}
    contract = (context or {}).get("cognitive_contract") or (task_meta or {}).get("cognitive_contract")
    planner_safety_rules = [
        "You have no independent goals.",
        "Prefer small, executable, low-risk steps.",
        "Return schema-compliant JSON under answer.",
    ]
    if contract:
        constraints = getattr(contract, "constraints", []) if not isinstance(contract, dict) else (contract.get("constraints") or [])
        for c in constraints:
            if c not in planner_safety_rules:
                planner_safety_rules.append(c)
        safety_level = getattr(contract, "safety_level", "") if not isinstance(contract, dict) else str(contract.get("safety_level") or "")
        if str(safety_level).lower() == "high":
            planner_safety_rules.append("CRITICAL: High-risk task detected. Be extremely cautious with destructive commands.")
    planner_phase_system_prompt = _build_planner_phase_system_prompt(
        loop,
        goal=goal,
        skill_suggestions=skill_suggestions,
        context=context or {},
        safety_rules=planner_safety_rules,
    )
    goal_payload = {
        "id": goal.goal_id,
        "title": goal.title,
        "description": goal.description,
        "domain": domain,
        "metadata": goal.metadata,
        "graph_facts": graph_facts,
    }
    question_payload = {
        "goal": goal_payload,
        "context": context or {},
        "known_skills": skill_suggestions,
        "available_sops": available_sops,
        "suggested_sop": suggested_sop,
        "available_exec_skills": available_exec_skills,
        "phase_payload": planning_phase_payload,
        "planner_lifecycle_payload": lifecycle,
        "planning_strategy_patch": (context or {}).get("planning_strategy_patch"),
        "planner_payload_variant": (context or {}).get("planner_payload_variant"),
        "phase_system_prompt": planner_phase_system_prompt,
        "prompt_layers": {
            "soul": str((goal.metadata or {}).get("soul_prompt") or ""),
            "skill_context": "Decompose the goal into executable steps with minimal risk.",
            "project_context": str((context or {}).get("historical_attempts") or ""),
            "hints": loop._build_planner_hints(context=context),
        },
        "plan_schema_hint": {
            "steps": [
                {
                    "step_id": "s1",
                    "description": "Natural language description of this step.",
                    "skill_id": "<optional skill_id from known_skills or null>",
                    "notes": "optional clarifications for Executor / tools",
                    "tool_intent": {
                        "expected_tool": "fs.read_file",
                        "allowed_fallback_families": ["filesystem", "shell"],
                        "why": "inspect target before mutation",
                    },
                }
            ]
        },
    }

    question = CouncilQuestion(
        topic="planner",
        importance=importance,
        prompt=planner_prompt,
        payload=question_payload,
    )
    decision = loop.council_manager.run_council("planner", question)
    plan_answer = decision.final.get("answer")
    try:
        with open("data/last_planner_raw.txt", "w") as f:
            f.write(str(plan_answer))
    except Exception:
        pass

    if isinstance(plan_answer, str):
        try:
            from quentin.cognitive.xml_integrity import repair_structured_response
            text, _repair_report = repair_structured_response(str(plan_answer or "").strip())
            # Prefer <final> block if present after XML repair.
            m_final = re.search(r"<final>\s*(.*?)\s*</final>", text, re.IGNORECASE | re.DOTALL)
            if m_final:
                text = str(m_final.group(1) or "").strip() or text
            else:
                m_fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.IGNORECASE | re.DOTALL)
                if m_fence:
                    text = str(m_fence.group(1) or "").strip() or text
            matches = re.findall(r"\{.*\}", text, re.DOTALL)
            plan_obj = None
            if matches:
                for m in sorted(matches, key=len, reverse=True):
                    try:
                        candidate = json.loads(m)
                        if isinstance(candidate, dict) and ("steps" in candidate or "action" in candidate):
                            plan_obj = candidate
                            break
                    except Exception:
                        continue
            if not plan_obj:
                plan_obj = json.loads(text)
        except Exception:
            logger.warning("CognitiveLoop._run_planner: hyper-robust parse failed; trying code-fence strip.")
            try:
                from quentin.council.manager import _strip_code_fences
                plan_obj = json.loads(_strip_code_fences(plan_answer))
            except Exception:
                logger.exception("CognitiveLoop._run_planner: total parse failure.")
                plan_obj = {}
    elif isinstance(plan_answer, dict):
        plan_obj = plan_answer
    else:
        plan_obj = {}

    steps_list = []
    raw_steps = plan_obj.get("steps") if isinstance(plan_obj, dict) else None
    # Robustness: some council/arbiter paths may return nested wrappers (answer.steps) or
    # place the plan at top-level. Prefer extracting a non-empty steps list before falling back.
    if not (isinstance(raw_steps, list) and raw_steps):
        try:
            final_obj = decision.final if hasattr(decision, "final") else None
        except Exception:
            final_obj = None
        if isinstance(final_obj, dict):
            ans = final_obj.get("answer")
            if isinstance(ans, dict):
                candidate = ans.get("steps")
                if isinstance(candidate, list) and candidate:
                    raw_steps = candidate
            if not (isinstance(raw_steps, list) and raw_steps):
                candidate = final_obj.get("steps")
                if isinstance(candidate, list) and candidate:
                    raw_steps = candidate
    if isinstance(raw_steps, list) and raw_steps:
        for s in raw_steps:
            steps_list.append(
                {
                    "step_id": s.get("step_id") or f"s{len(steps_list)+1}",
                    "description": s.get("description") or "",
                    "skill_id": s.get("skill_id"),
                    "notes": s.get("notes"),
                    "tool_intent": _normalize_step_tool_intent(s if isinstance(s, dict) else {}),
                }
            )
    else:
        steps_list = loop._build_planner_fallback_steps(task_text=task_text, context=context or {})
    for idx, st in enumerate(steps_list):
        if not isinstance(st, dict):
            continue
        st.setdefault("step_id", f"s{idx+1}")
        st["tool_intent"] = _normalize_step_tool_intent(st)

    steps_list, repair_notes = loop._repair_plan_quality(
        task_text=task_text,
        context=context or {},
        steps=steps_list,
    )
    discovery_guard = loop._assess_discovery_guard(steps_list)
    from quentin.utils.json import make_jsonable
    plan_payload = {
        "steps": steps_list,
        "known_skills": skill_suggestions,
        "council": decision.to_dict(),
        "planner_repairs": repair_notes,
        "discovery_guard": discovery_guard,
    }
    return {
        "goal_id": goal.goal_id,
        "raw_output": json.dumps(make_jsonable(plan_payload), ensure_ascii=False),
        "steps": steps_list,
        "used_skills": skill_suggestions,
    }


def build_planner_question_prompt(
    loop: Any,
    *,
    goal: Any,
    task_text: str,
    plan_schema_text: str,
    skill_suggestions: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> str:
    task = (context or {}).get("task")
    task_meta = getattr(task, "metadata", {}) if task is not None else {}

    iteration = context.get("iteration", 1) if context else 1
    if context:
        context = loop._prune_context_for_focus(context, iteration)

    real_tools = []
    executor = getattr(loop, "executor", None)
    tm = getattr(executor, "tool_manager", None) if executor is not None else None
    if tm:
        target_domain = getattr(goal, "domain", "core")
        real_tools = tm.get_tool_names_by_domain(str(target_domain))
    tool_inventory_line = f"\nAVAILABLE TOOLS (ONLY use these names): {real_tools}\n"

    kg_text = ""
    try:
        entities = [w for w in task_text.split() if len(w) > 4]
        from quentin.bootstrap.container import Container
        kg = Container().knowledge_graph
        kg_text = kg.get_context_text(entities)
    except Exception:
        pass

    if not loop._prompt_factory_enabled():
        forbidden_actions = context.get("forbidden_actions") if isinstance(context, dict) else []
        retry_error_patch = str((context or {}).get("retry_error_patch") or "").strip()
        strategy_patch_text = str((context or {}).get("planning_strategy_patch_text") or "").strip()
        retry_plan_delta_patch = str((context or {}).get("retry_plan_delta_patch") or "").strip()
        payload_variant_patch = str((context or {}).get("planner_payload_variant_patch") or "").strip()
        critical_instruction = str((context or {}).get("critical_instruction") or "").strip()
        forbidden_line = ""
        if isinstance(forbidden_actions, list) and forbidden_actions:
            forbidden_line = (
                "Recently blocked actions/commands (treat as forbidden unless user explicitly asks): "
                + ", ".join([str(x) for x in forbidden_actions[:6]])
                + ".\n"
            )
        return (
            "Decompose the given GOAL into a small sequence of executable steps.\n"
            "Use KNOWN SKILLS when clearly helpful, by referencing their skill_id.\n"
            "Before any write/delete/download/install action, include at least one Discovery step "
            "(ls/which/find/fs.read_file/grep/cat) to verify real environment state.\n"
            "Use the provided environment snapshot and any last-execution observations to prune steps that are already satisfied; prefer verify-only steps when appropriate.\n"
            "For each step, include tool_intent.expected_tool and a verification condition in notes.\n"
            "If a step explicitly mentions a tool name (e.g., fs.read_file/shell.run_command), executor tool call must stay aligned to that tool or documented compatible alias.\n"
            "Do not use interactive editors (nano/vim/vi/emacs) or guessed download URLs.\n"
            "For code edits, prefer fs.read_file + fs.search_replace/fs.write_file.\n"
            + forbidden_line +
            (retry_error_patch + "\n" if retry_error_patch else "") +
            (strategy_patch_text + "\n" if strategy_patch_text else "") +
            (retry_plan_delta_patch + "\n" if retry_plan_delta_patch else "") +
            (payload_variant_patch + "\n" if payload_variant_patch else "") +
            (
                "CRITICAL RESET INSTRUCTION:\n"
                + critical_instruction
                + "\n"
                if critical_instruction
                else ""
            ) +
            "You MUST return a JSON object under the 'answer' field with structure:\n"
            f"{plan_schema_text}"
        )

    contract = context.get("cognitive_contract") or (task_meta or {}).get("cognitive_contract")
    dynamic_safety_rules = [
        "You have no independent goals.",
        "Prefer small, executable, low-risk steps.",
        "Return schema-compliant JSON under answer.",
    ]
    if contract:
        for c in contract.constraints:
            if c not in dynamic_safety_rules:
                dynamic_safety_rules.append(c)
        if contract.safety_level == "high":
            dynamic_safety_rules.append("CRITICAL: High-risk task detected. Be extremely cautious with destructive commands.")

    system_prompt = _build_planner_phase_system_prompt(
        loop,
        goal=goal,
        skill_suggestions=skill_suggestions,
        context=context or {},
        safety_rules=dynamic_safety_rules,
    )
    proactive_data = context.get("proactive_perception") or (task_meta or {}).get("proactive_perception")
    perceived_block = ""
    if proactive_data:
        perceived_block = "\n*** START PERCEIVED EVIDENCE ***\n"
        if "files" in proactive_data:
            for idx, f in enumerate(proactive_data["files"]):
                perceived_block += f'<file id="f{idx}" name="{f["path"]}" hash="{f.get("hash", "unknown")}">\n{f.get("content", "[Empty]")}\n</file>\n'
        if "link_understanding" in proactive_data:
            for idx, l in enumerate(proactive_data["link_understanding"]):
                perceived_block += f'<url id="u{idx}" address="{l["url"]}">\n{l["summary"]}\n</url>\n'
        if "media_understanding" in proactive_data:
            for idx, m in enumerate(proactive_data["media_understanding"]):
                perceived_block += f'<media id="m{idx}" source="{m["source"]}" kind="{m.get("kind", "image")}">\n{m["text"]}\n</media>\n'
        if "ui_context" in proactive_data:
            ui = proactive_data["ui_context"]
            perceived_block += f'<ui_context elements="{ui.get("element_count")}">\n{ui.get("summary")}\n</ui_context>\n'
        perceived_block += "*** END PERCEIVED EVIDENCE ***\n"

    contract_summary = f"INTENT: {contract.intent}\nDOMAIN: {contract.domain}" if contract else "GENERAL TASK"
    correction_intensity = _resolve_correction_intensity_from_context(context or {})
    lifecycle = (context or {}).get("planner_lifecycle_payload") if isinstance((context or {}).get("planner_lifecycle_payload"), dict) else {}
    attempt_stage = str(lifecycle.get("stage") or "initial").strip().lower() or "initial"
    stage_directives = [str(x) for x in (lifecycle.get("directives") or []) if str(x).strip()]
    retry_error_patch = str((context or {}).get("retry_error_patch") or "").strip()
    strategy_patch_text = str((context or {}).get("planning_strategy_patch_text") or "").strip()
    retry_plan_delta_patch = str((context or {}).get("retry_plan_delta_patch") or "").strip()
    payload_variant_patch = str((context or {}).get("planner_payload_variant_patch") or "").strip()
    critical_instruction = str((context or {}).get("critical_instruction") or "").strip()
    user_prompt = (
        f"GOAL: {task_text}\n\n"
        f"--- TASK CONTRACT ---\n{contract_summary}\n---------------------\n"
        f"--- PLANNER LIFECYCLE STAGE ---\n{attempt_stage.upper()}\n-------------------------------\n"
        f"--- CORRECTION INTENSITY ---\n{correction_intensity.upper()}\n---------------------------\n"
        f"{perceived_block}\n"
        "Decompose the given GOAL into a small sequence of executable steps.\n"
        "Use KNOWN SKILLS when clearly helpful, by referencing their skill_id.\n"
        "Before any write/delete/download/install action, include at least one Discovery step "
        "(ls/which/find/fs.read_file/grep/cat) to verify real environment state.\n"
        "Use the provided environment snapshot and any last-execution observations to prune steps that are already satisfied; prefer verify-only steps when appropriate.\n"
        "For each step, include tool_intent.expected_tool and a verification condition in notes.\n"
        "If a step explicitly mentions a tool name (e.g., fs.read_file/shell.run_command), executor tool call must stay aligned to that tool or documented compatible alias.\n"
        + (
            ("Forbidden actions from recent guard feedback: "
             + ", ".join([str(x) for x in (context.get("forbidden_actions") or [])[:6]])
             + ".\n")
            if isinstance((context or {}).get("forbidden_actions"), list) and (context.get("forbidden_actions") or [])
            else ""
        )
        + (retry_error_patch + "\n" if retry_error_patch else "")
        + (strategy_patch_text + "\n" if strategy_patch_text else "")
        + (retry_plan_delta_patch + "\n" if retry_plan_delta_patch else "")
        + (payload_variant_patch + "\n" if payload_variant_patch else "")
        + (
            "--- CRITICAL RESET INSTRUCTION ---\n"
            + critical_instruction
            + "\n---------------------------------\n"
            if critical_instruction
            else ""
        )
        + "You MUST return a JSON object under the 'answer' field with structure:\n"
        f"{plan_schema_text}\n\n"
        "REMINDER: Your plan must fulfill the Success Anchors and adhere to all Primary Constraints defined in the System Rules.\n"
        + (
            ("--- STAGE DIRECTIVES ---\n" + "\n".join([f"- {x}" for x in stage_directives[:6]]) + "\n------------------------\n")
            if stage_directives
            else ""
        )
        + (
            "STUCK MODE OVERRIDE: You MUST include speculative execution probes (at least 2 hypotheses with concrete checks).\n"
            if attempt_stage == "stuck"
            else ""
        )
    )
    return f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}"


def build_executor_prompt_context(
    loop: Any,
    *,
    task: Any,
    goal: Any,
    progressive_pressure: bool,
) -> Dict[str, Any]:
    strict_reasons = loop._strict_reason_list_from_env()
    if not loop._prompt_factory_enabled():
        return {
            "soul_prompt": str((goal.metadata or {}).get("soul_prompt") or ""),
            "skill_prompt": "Execute safely and produce user-visible progress.",
            "project_context_prompt": str((goal.metadata or {}).get("project_context_prompt") or ""),
            "strict_reasons": strict_reasons,
        }
    hints: List[str] = []
    if progressive_pressure:
        hints.append(
            "You have performed multiple tool calls with no user-visible progress. "
            "Provide a brief progress update before continuing tool calls, or finish if possible."
        )
    strict_hint = loop._strict_reason_hint_from_env()
    if strict_hint:
        hints.append(strict_hint)
    attempt_eval = (task.metadata or {}).get("last_attempt_evaluation") if isinstance(task.metadata, dict) else {}
    correction_intensity = "medium"
    if isinstance(attempt_eval, dict):
        correction_intensity = str(attempt_eval.get("correction_intensity") or "medium").strip().lower() or "medium"
    phase_payload = build_phase_payload(
        phase="executing",
        correction_intensity=correction_intensity,
        reason="executor_entry",
    ).to_dict()
    enabled_tools: Dict[str, str] = {}
    tm = getattr(loop, "tool_manager", None)
    try:
        if tm is not None and hasattr(tm, "get_tool_summaries"):
            md = dict(getattr(task, "metadata", {}) or {})
            md.setdefault("domain", str(getattr(task, "domain", "") or "core"))
            md.setdefault("environment", str(getattr(task, "environment", "") or "sandbox"))
            md.setdefault("session_id", str(md.get("session_id") or getattr(task, "task_id", "") or "default"))
            enabled_tools = dict(tm.get_tool_summaries(max_words=12, context_metadata=md) or {})
    except Exception:
        enabled_tools = {}
    prompt = build_system_prompt(
        mode="minimal" if bool((task.metadata or {}).get("is_subagent", False)) else "full",
        identity="You are an execution agent in Quentin cognitive loop.",
        safety_rules=[
            "Prefer deterministic, low-risk actions.",
            "Use tools when needed; avoid unnecessary narration.",
            "Return machine-parseable output.",
        ],
        runtime_info=RuntimeInfo(
            agent_id="quentin-executor",
            workspace=str(loop.repo_root),
            os_name=platform.system().lower() or "unknown",
            model="executor-router",
            extras={"task_id": str(task.task_id), "goal_id": str(goal.goal_id)},
        ),
        enabled_tools=enabled_tools,
        project_context=str((goal.metadata or {}).get("project_context_prompt") or ""),
        hints=hints,
        phase_payload=phase_payload,
    )
    return {
        "soul_prompt": str((goal.metadata or {}).get("soul_prompt") or ""),
        "skill_prompt": prompt,
        "project_context_prompt": str((goal.metadata or {}).get("project_context_prompt") or ""),
        "forbidden_actions": list((task.metadata or {}).get("forbidden_actions") or []),
        "strict_reasons": strict_reasons,
        "phase_payload": phase_payload,
    }


def build_planner_hints(loop: Any, context: Optional[Dict[str, Any]]) -> List[str]:
    hints = [
        "Prefer concrete steps.",
        "Reference known skills when helpful.",
        "Never use interactive editors like nano/vim; use fs.read_file + fs.search_replace/fs.write_file.",
        "Do not install/download tooling via guessed URLs; only use user-provided URLs.",
        "For write/delete/download/install actions, include a discovery precheck first.",
        "When you name an explicit tool in a step description, keep that tool intent stable for executor alignment.",
    ]
    try:
        from quentin.kernel.path_guard import PathGuard
        allowed = PathGuard(Path(".").resolve(), allowed_roots=None).allowed_roots
        if allowed:
            hints.append(
                "WRITE POLICY: Allowed write roots are "
                + ", ".join([f"{root}/" for root in allowed])
                + ". Use fs.get_write_policy to verify before writing."
            )
    except Exception:
        pass
    strict_hint = loop._strict_reason_hint_from_env()
    if strict_hint:
        hints.append(strict_hint)
    if not isinstance(context, dict):
        return hints
    note = str(context.get("self_awareness_note") or "").strip()
    if note:
        hints.append(note)
    candidate_files = context.get("candidate_files")
    if isinstance(candidate_files, list) and candidate_files:
        hints.append("Candidate files: " + ", ".join([str(x) for x in candidate_files[:6]]))
    forbidden_actions = context.get("forbidden_actions")
    if isinstance(forbidden_actions, list) and forbidden_actions:
        hints.append("Forbidden actions from recent guard feedback: " + ", ".join([str(x) for x in forbidden_actions[:6]]))
    strategy_patch = context.get("planning_strategy_patch")
    if isinstance(strategy_patch, dict):
        category = str(strategy_patch.get("category") or "").strip()
        directives = [str(x) for x in (strategy_patch.get("directives") or []) if str(x).strip()]
        if category:
            hints.append("Planning strategy patch category: " + category)
        if directives:
            hints.append("Planning strategy directives: " + " | ".join(directives[:2]))
    retry_plan_delta = context.get("retry_plan_delta")
    if isinstance(retry_plan_delta, dict) and retry_plan_delta:
        hints.append(
            "Retry plan delta required: previous_step_count="
            + str(int(retry_plan_delta.get("previous_step_count") or 0))
        )
    payload_variant = context.get("planner_payload_variant")
    if isinstance(payload_variant, dict) and payload_variant:
        vid = str(payload_variant.get("variant_id") or "").strip()
        attempt_band = str(payload_variant.get("attempt_band") or "").strip()
        vdirs = [str(x) for x in (payload_variant.get("directives") or []) if str(x).strip()]
        if vid:
            hints.append("Planner payload variant id: " + vid)
        if attempt_band:
            hints.append("Planner attempt band: " + attempt_band)
        if vdirs:
            hints.append("Planner payload variant directives: " + " | ".join(vdirs[:2]))
    critical_instruction = str(context.get("critical_instruction") or "").strip()
    if critical_instruction:
        hints.append("Critical reset instruction active: forget previous failing decomposition and re-plan from Goal.")
    return hints
