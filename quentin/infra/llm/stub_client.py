from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional

from quentin.infra.llm.base import ModelClient, ModelResponse, UsageMetadata
from quentin.infra.llm.registry import registry


def _msg_text(msg: Dict[str, Any]) -> str:
    c = msg.get("content")
    if isinstance(c, str):
        return c
    # Some call sites use OpenAI-like content lists.
    if isinstance(c, list):
        parts: List[str] = []
        for item in c:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "\n".join([p for p in parts if p])
    return str(c or "")


def _looks_executor(system_prompt: str) -> bool:
    sp = (system_prompt or "").lower()
    return "hardcore execution agent" in sp or '"call_tool"' in sp and "only perform actions" in sp


def _looks_tool_router(system_prompt: str, user_prompt: str) -> bool:
    sp = (system_prompt or "").lower()
    up = (user_prompt or "").lower()
    return ("tool router" in sp) or ("pick the 5 most relevant tool names" in up)


def _extract_council_name(system_prompt: str) -> str:
    # Matches CouncilManager base_system_prompt: "Council: {name}. Topic: ..."
    sp = system_prompt or ""
    key = "Council:"
    if key not in sp:
        # Arbiter path uses "You are the arbiter for council 'X'."
        low = sp.lower()
        if "arbiter for council" in low:
            # Try single quotes first.
            if "council '" in low:
                try:
                    after = sp.split("council '", 1)[1]
                    name = after.split("'", 1)[0].strip()
                    return name.lower()
                except Exception:
                    pass
            # Fallback: "council \"X\""
            if 'council "' in low:
                try:
                    after = sp.split('council "', 1)[1]
                    name = after.split('"', 1)[0].strip()
                    return name.lower()
                except Exception:
                    pass
        # Phase system prompts (OpenClaw parity) often omit "Council:" but include identity lines.
        if "planning agent in quentin cognitive loop" in low:
            return "planner"
        if "reflection agent in quentin cognitive loop" in low:
            return "reflection"
        if "decide whether the given goal can be considered sufficiently done" in low:
            return "done"
        if "focused sensing active" in low or "pre-sensing" in low or "pre_sensing" in low:
            return "pre_sensing"
        return ""
    after = sp.split(key, 1)[1].strip()
    # "planner. Topic: ..." -> "planner"
    name = after.split(".", 1)[0].strip()
    return name.lower()


def _safe_json_loads(text: str) -> Dict[str, Any]:
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _bench_scenario_from_goal_text(text: str) -> str:
    t = str(text or "")
    marker = "BENCH_SCENARIO:"
    if marker not in t:
        return ""
    return t.split(marker, 1)[1].split()[0].strip().lower()


def stub_generate_text(*, system_prompt: str, user_prompt: str) -> str:
    """
    Synchronous stub generator.

    Why this exists:
    - The cognitive loop frequently calls `call_llm` from inside an active asyncio loop
      (via LaneOrchestrator.run_sync -> asyncio.run).
    - The normal call_llm path uses a ThreadPoolExecutor bridge to run async clients.
    - Some sandboxes disallow thread creation (OSError: [Errno 1] Operation not permitted).

    For provider="stub", we bypass async + threads entirely.
    """
    if _looks_tool_router(system_prompt, user_prompt):
        # Executor fast tool-filter expects a comma-separated list of tool names (not JSON).
        return "fs.read_file, fs.search_replace, fs.write_file, shell.run_command, ls"
    council = _extract_council_name(system_prompt)
    client = StubClient(name="stub-model", provider="stub")
    if council:
        return client._generate_council(council=council, system_prompt=system_prompt, user_prompt=user_prompt)
    if _looks_executor(system_prompt):
        return client._generate_executor(system_prompt=system_prompt, user_prompt=user_prompt)
    return json.dumps(
        {"verdict": "undecided", "reasoning": "stub:unrecognized_prompt", "answer": {"text": (user_prompt or "")[:2000]}},
        ensure_ascii=False,
    )


class StubClient(ModelClient):
    """
    Offline stub provider for deterministic benchmark runs.

    This is not a "smart" model. It's a policy-driven response generator that:
    - returns schema-compliant JSON for councils (planner/done/reflection)
    - returns schema-compliant JSON for the executor (call_tool)
    """

    async def generate(self, messages: List[Dict[str, Any]], **kwargs: Any) -> ModelResponse:
        system_prompt = _msg_text(messages[0]) if messages else ""
        user_prompt = _msg_text(messages[-1]) if messages else ""

        if _looks_tool_router(system_prompt, user_prompt):
            text = "fs.read_file, fs.search_replace, fs.write_file, shell.run_command, ls"
        else:
            council = _extract_council_name(system_prompt)
            if council:
                text = self._generate_council(council=council, system_prompt=system_prompt, user_prompt=user_prompt)
            elif _looks_executor(system_prompt):
                text = self._generate_executor(system_prompt=system_prompt, user_prompt=user_prompt)
            else:
                # Default safe envelope: JSON object to keep callers resilient.
                text = json.dumps(
                    {"verdict": "undecided", "reasoning": "stub:unrecognized_prompt", "answer": {"text": user_prompt[:2000]}},
                    ensure_ascii=False,
                )

        usage = UsageMetadata(prompt_tokens=0, completion_tokens=0, total_tokens=0, cost_usd=0.0)
        return ModelResponse(text=text, usage=usage, raw={"provider": "stub"})

    async def stream(self, messages: List[Dict[str, Any]], **kwargs: Any) -> AsyncIterator[str]:
        # Minimal stream: yield the whole completion once.
        resp = await self.generate(messages, **kwargs)
        yield resp.text

    async def embed(self, texts: List[str], **kwargs: Any) -> List[List[float]]:
        # Deterministic tiny embeddings.
        return [[0.0, 0.0, 0.0] for _ in (texts or [])]

    def __init__(
        self,
        *,
        name: str,
        provider: str,
        retry_strategy: Any = None,
        auth_profile_id: Optional[str] = None,
        **_ignored: Any,
    ) -> None:
        # ModelClientFactory passes transport/provider-specific kwargs like timeout/api_key/base_url.
        # StubClient must accept them to remain a drop-in adapter.
        super().__init__(
            name=name,
            provider=provider,
            retry_strategy=retry_strategy,
            auth_profile_id=auth_profile_id,
        )

    def _generate_council(self, *, council: str, system_prompt: str, user_prompt: str) -> str:
        payload_obj = _safe_json_loads(user_prompt)

        # Council member calls use {"prompt": ..., "payload": {...}}.
        # Arbiter calls use {"question": {...}, "member_replies": [...], "instructions": "..."}.
        if isinstance(payload_obj.get("question"), dict):
            q = payload_obj.get("question") if isinstance(payload_obj.get("question"), dict) else {}
            prompt = str(q.get("prompt") or "")
            payload = q.get("payload") if isinstance(q.get("payload"), dict) else {}
        else:
            prompt = str(payload_obj.get("prompt") or "")
            payload = payload_obj.get("payload") if isinstance(payload_obj.get("payload"), dict) else {}

        goal = payload.get("goal") if isinstance(payload.get("goal"), dict) else {}
        goal_text = " ".join([str(goal.get("title") or ""), str(goal.get("description") or ""), str(prompt or "")])
        scenario = _bench_scenario_from_goal_text(goal_text)

        if council == "planner":
            # Return plan under final.answer (CouncilManager expects JSON dict output).
            if scenario == "tool_error":
                steps = [
                    {
                        "step_id": "s1",
                        "description": (
                            "BENCH_STEP: tool_error\n"
                            "Read the file 'generated/benchmarks/bench_missing_file_12345.txt' using fs.read_file."
                        ),
                        "skill_id": None,
                        "notes": "intentionally triggers tool_execution_error on attempt 1",
                        "tool_intent": {
                            "expected_tool": "fs.read_file",
                            "allowed_fallback_families": ["filesystem", "shell"],
                            "why": "bench: force tool error classification",
                        },
                    }
                ]
            elif scenario == "logic_loop":
                steps = [
                    {
                        "step_id": "s1",
                        "description": "BENCH_STEP: echo_loop\nExecute a tool call loop now to trigger repeated_tool_call_loop.",
                        "skill_id": None,
                        "notes": "intentionally triggers repeated_tool_call_loop (logic_path_error)",
                        "tool_intent": {
                            "expected_tool": "shell.run_command",
                            "allowed_fallback_families": ["shell"],
                            "why": "bench: force logic loop classification",
                        },
                    }
                ]
            else:
                steps = [
                    {
                        "step_id": "s1",
                        "description": "BENCH_STEP: write_success_file",
                        "skill_id": None,
                        "notes": "default stub plan: write a bench marker file",
                        "tool_intent": {
                            "expected_tool": "fs.write_file",
                            "allowed_fallback_families": ["filesystem"],
                            "why": "bench: produce deterministic done marker",
                        },
                    }
                ]
            # Avoid planner-quality repair fallback (which replaces <=1-step plans).
            steps.extend(
                [
                    {
                        "step_id": f"s{len(steps)+1}",
                        "description": "Summarize current attempt status in one line (no tool call).",
                        "skill_id": None,
                        "notes": "bench:padding_step_no_tool",
                        "tool_intent": {"expected_tool": "", "allowed_fallback_families": [], "why": "bench:no_tool"},
                    },
                    {
                        "step_id": f"s{len(steps)+2}",
                        "description": "Reflect on next action briefly (no tool call).",
                        "skill_id": None,
                        "notes": "bench:padding_step_no_tool",
                        "tool_intent": {"expected_tool": "", "allowed_fallback_families": [], "why": "bench:no_tool"},
                    },
                ]
            )
            out = {
                "verdict": "ok",
                "reasoning": f"stub:planner scenario={scenario or 'default'}",
                "answer": {"steps": steps},
            }
            return json.dumps(out, ensure_ascii=False)

        if council == "done":
            exec_summary = payload.get("execution_summary") if isinstance(payload.get("execution_summary"), dict) else {}
            final_output = str(exec_summary.get("final_output") or "")
            actions_summary = str(exec_summary.get("actions_summary") or "")
            logs_excerpt = str(exec_summary.get("logs_excerpt") or "")
            is_done = any("BENCH_DONE" in x for x in (final_output, actions_summary, logs_excerpt))
            out = {
                "verdict": "done" if is_done else "not_done",
                "reasoning": "stub:done_check based_on_final_output_marker",
                "is_done": bool(is_done),
            }
            return json.dumps(out, ensure_ascii=False)

        if council == "reflection":
            attempt_eval = payload.get("attempt_evaluation") if isinstance(payload.get("attempt_evaluation"), dict) else {}
            category = str(attempt_eval.get("category") or "").strip().lower()
            intensity = str(attempt_eval.get("correction_intensity") or "").strip().lower()

            # Force an explicit plan override so the next attempt uses a different branch.
            new_plan = {
                "steps": [
                    {
                        "step_id": "s1",
                        "description": "BENCH_STEP: write_success_file",
                        "skill_id": None,
                        "notes": f"reflection_override category={category} intensity={intensity}",
                        "tool_intent": {
                            "expected_tool": "fs.write_file",
                            "allowed_fallback_families": ["filesystem"],
                            "why": "bench: deterministic recovery plan",
                        },
                    }
                ]
            }
            out = {
                "verdict": "ok",
                "reasoning": f"stub:reflection override_plan category={category} intensity={intensity}",
                "answer": {
                    "action": "retry",
                    "new_plan": new_plan,
                    "goal_adjustment": None,
                    "skill_ideas": [],
                },
            }
            return json.dumps(out, ensure_ascii=False)

        if council == "pre_sensing":
            # Semantic pre-sensing must be conservative in isolated benches.
            out = {"verdict": "not_done", "evidence_summary": "stub:pre_sensing disabled/insufficient evidence", "confidence": 0.0}
            return json.dumps(out, ensure_ascii=False)

        # Unknown councils: keep JSON envelope
        return json.dumps({"verdict": "undecided", "reasoning": f"stub:unknown_council:{council}", "answer": {}}, ensure_ascii=False)

    def _generate_executor(self, *, system_prompt: str, user_prompt: str) -> str:
        payload = _safe_json_loads(user_prompt)
        step = payload.get("step") if isinstance(payload.get("step"), dict) else {}
        desc = str(step.get("description") or "")
        _ = payload.get("iteration")  # iteration is handled by executor loop; stub is stateless.

        # Logic loop scenario: repeat a harmless successful command until repeated-call guard triggers.
        if "echo_loop" in desc:
            return json.dumps(
                {
                    "status": "ok",
                    "result": "bench:echo_loop_keep_going",
                    "call_tool": {"tool_name": "shell.run_command", "args": {"command": "echo bench-loop"}},
                },
                ensure_ascii=False,
            )

        # Recovery/success: write a marker file under allowed roots.
        if "write_success_file" in desc:
            return json.dumps(
                {
                    "status": "ok",
                    "result": "BENCH_DONE: wrote marker file",
                    "call_tool": {
                        "tool_name": "fs.write_file",
                        "args": {"path": "generated/benchmarks/bench_done_marker.txt", "content": "BENCH_DONE\\n"},
                    },
                },
                ensure_ascii=False,
            )

        # Default: no-op finish.
        return json.dumps({"status": "ok", "result": "stub:noop", "call_tool": None}, ensure_ascii=False)


registry.register("stub", StubClient)
