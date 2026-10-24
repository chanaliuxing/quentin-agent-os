from __future__ import annotations

import json
import os
import re
import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "1" if default else "0")
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_think_level(v: str) -> str:
    val = str(v or "").strip().lower()
    if val in {"off", "low", "medium", "high"}:
        return val
    return "off"


def _env_csv(name: str, default: str) -> List[str]:
    raw = str(os.getenv(name, default) or "")
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _directive_allowed(name: str) -> bool:
    allow = _env_csv("QUENTIN_INPUT_DIRECTIVE_ALLOWLIST", "thinking")
    if not allow or "*" in allow:
        return True
    return str(name or "").strip().lower() in set(allow)


def _directive_authorized(name: str, *, metadata: Dict[str, Any] | None) -> bool:
    if not _env_bool("QUENTIN_INPUT_DIRECTIVE_AUTHZ_ENABLED", False):
        return True
    md = metadata or {}
    directive = str(name or "").strip().lower()
    role = str(md.get("role") or md.get("user_role") or "user").strip().lower()
    allowed_roles = set(_env_csv("QUENTIN_INPUT_DIRECTIVE_AUTHZ_ROLES", "owner,admin,maintainer"))
    if role not in allowed_roles:
        return False
    # Optional session scope gate for directive persistence.
    if directive in {"thinking", "model", "tool"}:
        scope = str(md.get("session_scope") or "private").strip().lower()
        allow_shared = _env_bool("QUENTIN_INPUT_DIRECTIVE_AUTHZ_ALLOW_SHARED_SESSION", False)
        if scope == "shared" and not allow_shared:
            return False
    return True


def _record_blocked_directive(out: InputPreprocessResult, name: str) -> None:
    existing = out.metadata_updates.get("directive_authz_blocked")
    blocked = list(existing) if isinstance(existing, list) else []
    key = str(name or "").strip().lower()
    if key and key not in blocked:
        blocked.append(key)
    out.metadata_updates["directive_authz_blocked"] = blocked


@dataclass
class InputPreprocessResult:
    cleaned_text: str
    command_name: str = ""
    command_args: str = ""
    directives: Dict[str, str] = field(default_factory=dict)
    mentions: List[str] = field(default_factory=list)
    metadata_updates: Dict[str, Any] = field(default_factory=dict)
    route_domain: str = ""
    inline_action: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandExecutionContext:
    loop: Any
    task: Any
    parsed: InputPreprocessResult
    session_id: str


CommandHandler = Callable[[CommandExecutionContext], Awaitable[Dict[str, Any]]]


class InputCommandRegistry:
    def __init__(self) -> None:
        self._handlers: Dict[str, CommandHandler] = {}

    def register(self, name: str, handler: CommandHandler) -> None:
        key = str(name or "").strip().lower()
        if not key:
            return
        self._handlers[key] = handler

    def get(self, name: str) -> Optional[CommandHandler]:
        key = str(name or "").strip().lower()
        if not key:
            return None
        if key not in self._handlers:
            return None
        allowed = str(os.getenv("QUENTIN_INPUT_COMMAND_ALLOWLIST", "*") or "*").strip()
        if allowed in {"", "*"}:
            return self._handlers[key]
        allow_set = {x.strip().lower() for x in allowed.split(",") if x.strip()}
        return self._handlers[key] if key in allow_set else None

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    def list_commands(self) -> List[str]:
        return sorted(self._handlers.keys())


_registry_singleton: Optional[InputCommandRegistry] = None
_registry_plugins_loaded = False


def get_input_command_registry() -> InputCommandRegistry:
    global _registry_singleton, _registry_plugins_loaded
    if _registry_singleton is None:
        _registry_singleton = InputCommandRegistry()
        _registry_singleton.register("status", _handle_status_command)
        _registry_singleton.register("reset", _handle_reset_command)
    if not _registry_plugins_loaded:
        _load_command_plugins(_registry_singleton)
        _registry_plugins_loaded = True
    return _registry_singleton


def _load_command_plugins(registry: InputCommandRegistry) -> None:
    """
    Load external command handlers from env:
    QUENTIN_INPUT_COMMAND_HANDLERS="pkg.mod:register_fn,other.mod:install"

    Each function will be called with (registry).
    """
    raw = str(os.getenv("QUENTIN_INPUT_COMMAND_HANDLERS", "") or "").strip()
    if not raw:
        return
    for item in raw.split(","):
        spec = item.strip()
        if not spec:
            continue
        if ":" not in spec:
            logger.warning("input_preprocessor: invalid command plugin spec (expected module:function): %s", spec)
            continue
        mod_name, fn_name = spec.split(":", 1)
        mod_name = mod_name.strip()
        fn_name = fn_name.strip()
        if not mod_name or not fn_name:
            logger.warning("input_preprocessor: invalid command plugin spec: %s", spec)
            continue
        try:
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, fn_name)
            fn(registry)
        except Exception as e:  # noqa: BLE001
            logger.warning("input_preprocessor: failed loading command plugin %s: %s", spec, e)


def _reset_command_registry_for_tests() -> None:
    global _registry_singleton, _registry_plugins_loaded
    _registry_singleton = None
    _registry_plugins_loaded = False


def _parse_route_map(raw: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for item in str(raw or "").split(","):
        part = item.strip()
        if not part or ":" not in part:
            continue
        k, v = part.split(":", 1)
        key = k.strip().lower()
        val = v.strip().lower()
        if key and val:
            mapping[key] = val
    return mapping


def preprocess_input(*, text: str, default_domain: str, metadata: Dict[str, Any] | None = None) -> InputPreprocessResult:
    content = str(text or "")
    cleaned = content.strip()
    out = InputPreprocessResult(cleaned_text=cleaned)

    if not _env_bool("QUENTIN_INPUT_PREPROCESS_ENABLED", True):
        return out

    command_prefix = str(os.getenv("QUENTIN_INPUT_COMMAND_PREFIX", "/") or "/")
    command_registry = get_input_command_registry()

    # 1) Command detection: only if first token is command.
    if _env_bool("QUENTIN_INPUT_COMMANDS_ENABLED", True) and cleaned.startswith(command_prefix):
        first_line = cleaned.splitlines()[0].strip()
        first_token = first_line.split()[0]
        cmd = first_token[len(command_prefix):].strip().lower()
        if command_registry.has(cmd):
            out.command_name = cmd
            out.command_args = first_line[len(first_token):].strip()
            out.cleaned_text = cleaned
            return out

    # 1.5) Inline deterministic action syntax:
    # /tool <tool_name> <json_args>
    if _env_bool("QUENTIN_INPUT_INLINE_ACTIONS_ENABLED", True):
        m_tool = re.match(r"^\s*/tool\s+([A-Za-z0-9_.-]+)\s+(\{.*\})\s*$", cleaned, re.DOTALL)
        if m_tool:
            tool_name = str(m_tool.group(1) or "").strip()
            raw_args = str(m_tool.group(2) or "").strip()
            args_obj: Dict[str, Any] = {}
            try:
                parsed = json.loads(raw_args)
                if isinstance(parsed, dict):
                    args_obj = parsed
            except Exception:
                args_obj = {}
            allow_tools = _env_csv(
                "QUENTIN_INPUT_INLINE_ACTION_TOOL_ALLOWLIST",
                "fs.exists,fs.read_file,shell.run_command",
            )
            if ("*" in allow_tools) or (tool_name.lower() in set(allow_tools)):
                out.inline_action = {
                    "kind": "tool_call",
                    "tool_name": tool_name,
                    "arguments": args_obj,
                }
                out.metadata_updates["inline_action"] = dict(out.inline_action)
                out.cleaned_text = cleaned
                return out

    # 2) Mentions extraction.
    if _env_bool("QUENTIN_INPUT_MENTIONS_ENABLED", True):
        mentions = [m.lower() for m in re.findall(r"@([A-Za-z0-9_-]+)", cleaned)]
        dedup: List[str] = []
        for m in mentions:
            if m not in dedup:
                dedup.append(m)
        out.mentions = dedup
        if dedup:
            out.metadata_updates["mentions"] = dedup
            cleaned = re.sub(r"@([A-Za-z0-9_-]+)", "", cleaned).strip()

        if _env_bool("QUENTIN_INPUT_ROUTE_BY_MENTION", False):
            route_map = _parse_route_map(
                os.getenv("QUENTIN_INPUT_MENTION_ROUTE_MAP", "research:research,coding:maintenance")
            )
            for m in dedup:
                dom = route_map.get(m)
                if dom:
                    out.route_domain = dom
                    break

    # 3) Inline directives extraction.
    if _env_bool("QUENTIN_INPUT_DIRECTIVES_ENABLED", True):
        # /thinking high
        m = re.search(r"(?:^|\s)/thinking\s+(off|low|medium|high)(?:\s|$)", cleaned, re.IGNORECASE)
        if m:
            level = _normalize_think_level(m.group(1))
            if _directive_allowed("thinking") and _directive_authorized("thinking", metadata=metadata):
                out.directives["thinking"] = level
                if _env_bool("QUENTIN_INPUT_DIRECTIVE_PERSIST", True):
                    out.metadata_updates["think_level"] = level
            elif _directive_allowed("thinking"):
                _record_blocked_directive(out, "thinking")
            cleaned = re.sub(r"(?:^|\s)/thinking\s+(off|low|medium|high)(?:\s|$)", " ", cleaned, flags=re.IGNORECASE).strip()

        # /model <model_name>
        m_model = re.search(r"(?:^|\s)/model\s+([A-Za-z0-9._:-]+)(?:\s|$)", cleaned, re.IGNORECASE)
        if m_model:
            model_name = str(m_model.group(1) or "").strip()
            allowed_models = set(_env_csv("QUENTIN_INPUT_DIRECTIVE_MODEL_ALLOWLIST", "*"))
            model_allowed = ("*" in allowed_models) or (model_name.lower() in allowed_models)
            if _directive_allowed("model") and _directive_authorized("model", metadata=metadata) and model_allowed:
                out.directives["model"] = model_name
                if _env_bool("QUENTIN_INPUT_DIRECTIVE_PERSIST", True):
                    out.metadata_updates["model_override"] = model_name
            elif _directive_allowed("model"):
                _record_blocked_directive(out, "model")
            cleaned = re.sub(r"(?:^|\s)/model\s+([A-Za-z0-9._:-]+)(?:\s|$)", " ", cleaned, flags=re.IGNORECASE).strip()

        # /tool <profile> (directive mode; distinct from /tool <name> {json_args} inline action)
        m_tool = re.search(r"(?:^|\s)/tool\s+([A-Za-z0-9._:-]+)(?:\s|$)", cleaned, re.IGNORECASE)
        if m_tool:
            tool_profile = str(m_tool.group(1) or "").strip().lower()
            allowed_profiles = set(_env_csv("QUENTIN_INPUT_DIRECTIVE_TOOL_ALLOWLIST", "safe,code,research,admin"))
            profile_allowed = ("*" in allowed_profiles) or (tool_profile in allowed_profiles)
            if _directive_allowed("tool") and _directive_authorized("tool", metadata=metadata) and profile_allowed:
                out.directives["tool"] = tool_profile
                if _env_bool("QUENTIN_INPUT_DIRECTIVE_PERSIST", True):
                    out.metadata_updates["tool_profile"] = tool_profile
            elif _directive_allowed("tool"):
                _record_blocked_directive(out, "tool")
            cleaned = re.sub(r"(?:^|\s)/tool\s+([A-Za-z0-9._:-]+)(?:\s|$)", " ", cleaned, flags=re.IGNORECASE).strip()

    out.cleaned_text = re.sub(r"\s+", " ", cleaned).strip()
    if not out.cleaned_text:
        out.cleaned_text = str(text or "").strip()
    if not out.route_domain:
        out.route_domain = str(default_domain or "").strip()
    return out


async def execute_command_async(*, loop: Any, task: Any, parsed: InputPreprocessResult) -> Optional[Dict[str, Any]]:
    cmd = str(parsed.command_name or "").strip().lower()
    if not cmd:
        return None

    command_registry = get_input_command_registry()
    handler = command_registry.get(cmd)
    if handler is None:
        return None

    session_id = str((task.metadata or {}).get("session_id") or task.task_id or "global")
    return await handler(
        CommandExecutionContext(
            loop=loop,
            task=task,
            parsed=parsed,
            session_id=session_id,
        )
    )


async def execute_inline_action_async(*, loop: Any, task: Any, parsed: InputPreprocessResult) -> Optional[Dict[str, Any]]:
    action = parsed.inline_action if isinstance(parsed.inline_action, dict) else {}
    if not action:
        return None
    if str(action.get("kind") or "") != "tool_call":
        return None

    tool_name = str(action.get("tool_name") or "").strip()
    arguments = action.get("arguments") if isinstance(action.get("arguments"), dict) else {}
    if not tool_name:
        return None

    executor = getattr(loop, "executor", None)
    tool_manager = getattr(executor, "tool_manager", None) if executor is not None else None
    if tool_manager is None:
        return {
            "status": "fallback",
            "final_output": "inline action skipped: tool manager unavailable, fallback to planner",
            "actions_summary": "inline_action:fallback_no_tool_manager",
        }

    if tool_name == "shell.run_command":
        cmd = str(arguments.get("command") or "").strip()
        if not cmd:
            return {
                "status": "fallback",
                "final_output": "inline action skipped: empty shell command, fallback to planner",
                "actions_summary": "inline_action:fallback_empty_shell_command",
            }
        allowed_heads = _env_csv("QUENTIN_INPUT_INLINE_ACTION_SHELL_ALLOWLIST", "pwd,ls,id,which")
        head = cmd.split()[0].strip().lower() if cmd.split() else ""
        if not (("*" in allowed_heads) or (head in set(allowed_heads))):
            return {
                "status": "fallback",
                "final_output": "inline action skipped: shell command not allowlisted, fallback to planner",
                "actions_summary": "inline_action:fallback_shell_not_allowlisted",
            }

    from quentin.tools.schemas import ToolCallRequest
    from quentin.tools.manager import ToolCallContext

    session_id = str((task.metadata or {}).get("session_id") or task.task_id or "global")
    req = ToolCallRequest(tool_name=tool_name, payload=arguments)
    md: Dict[str, Any] = {"session_id": session_id, "inline_action": True}
    # Propagate repo_root so OpenClaw-parity tools (execution_parity) can isolate
    # their state (they default to ctx.metadata.repo_root or ".").
    try:
        if isinstance(task.metadata, dict):
            rr = task.metadata.get("repo_root")
            if rr:
                md["repo_root"] = str(rr)
    except Exception:
        pass
    ctx = ToolCallContext(metadata=md, cancel_token=(task.metadata or {}).get("cancel_token"))
    try:
        out = await tool_manager.call_tool(req, ctx)
        if not bool(getattr(out, "success", False)):
            return {
                "status": "fallback",
                "final_output": f"inline action failed: {getattr(out, 'error', 'unknown')}; fallback to planner",
                "actions_summary": "inline_action:fallback_tool_error",
            }
        return {
            "status": "ok",
            "final_output": str(getattr(out, "output", "")),
            "actions_summary": f"inline_action:tool_call:{tool_name}",
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("input_preprocessor: inline action tool call failed: %s", e)
        return {
            "status": "fallback",
            "final_output": "inline action exception; fallback to planner",
            "actions_summary": "inline_action:fallback_exception",
        }


async def _handle_status_command(ctx: CommandExecutionContext) -> Dict[str, Any]:
    payload = {
        "command": "status",
        "session_id": ctx.session_id,
        "domain": str(getattr(ctx.task, "domain", "") or ""),
        "environment": str(getattr(ctx.task, "environment", "") or ""),
        "think_level": str((ctx.task.metadata or {}).get("think_level", "off")),
        "mentions": list(ctx.parsed.mentions or []),
        "directives": dict(ctx.parsed.directives or {}),
    }
    return {"status": "ok", "final_output": json.dumps(payload, ensure_ascii=False), "actions_summary": "command:/status"}


async def _handle_reset_command(ctx: CommandExecutionContext) -> Dict[str, Any]:
    if isinstance(ctx.task.metadata, dict):
        ctx.task.metadata["think_level"] = "off"
        ctx.task.metadata.pop("mentions", None)
        ctx.task.metadata["input_preprocessor_reset"] = True
    # Best-effort lightweight reset actions.
    try:
        if getattr(ctx.loop, "system_event_queue", None) is not None:
            ctx.loop.system_event_queue.consume_pending(session_id=ctx.session_id)
    except Exception:
        pass
    return {
        "status": "ok",
        "final_output": "session controls reset: think_level=off, mentions cleared",
        "actions_summary": "command:/reset",
    }
