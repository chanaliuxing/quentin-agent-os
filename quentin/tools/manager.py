from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Callable, List, Optional, Awaitable, Tuple
import asyncio
import inspect
import time
import uuid
import shlex
import json
import os
import fnmatch
import logging
from threading import Lock, RLock
from pathlib import Path

logger = logging.getLogger(__name__)

from quentin.tools.schemas import ToolSpec, ToolCallRequest, ToolCallResult
from quentin.tools.schema_transformer import (
    normalize_tool_schema,
    normalize_tool_params,
    patch_tool_schema_for_claude_compatibility
)
from quentin.infra.tools.output_sanitizer import sanitize_tool_output
from quentin.infra.concurrency.cancellation import CancellationToken, CancelledError
from quentin.tools.pipeline import ToolPipeline

from quentin.tools.middleware.base import ToolMiddleware, ToolMiddlewareChain, BeforeOutcome, AfterOutcome
from quentin.tools.middleware.auth_rotator import AuthRotationMiddleware
from quentin.tools.middleware.security_audit import SecurityAuditMiddleware


@dataclass
class ToolPolicy:
    allow: Optional[List[str]] = None
    deny: Optional[List[str]] = None
    profile: Optional[str] = None


@dataclass
class ToolCallContext:
    policies: Optional[List[ToolPolicy]] = None
    metadata: Optional[Dict[str, Any]] = None
    trace_id: Optional[str] = None
    cancel_token: Optional[CancellationToken] = None


def resolve_effective_tool_policy(
    *,
    global_policy: ToolPolicy,
    stacked: List[ToolPolicy],
) -> ToolPolicy:
    deny: List[str] = []
    allow_sets: List[List[str]] = []
    profile: Optional[str] = None

    for p in [global_policy, *stacked]:
        if p.deny:
            deny.extend([str(x) for x in p.deny if x])
        if p.allow:
            allow_sets.append([str(x) for x in p.allow if x])
        if p.profile:
            profile = str(p.profile)

    allow: Optional[List[str]] = None
    if allow_sets:
        merged: List[str] = []
        seen = set()
        for lst in allow_sets:
            for item in lst:
                if item not in seen:
                    merged.append(item)
                    seen.add(item)
        allow = merged

    if deny:
        deny = list(dict.fromkeys(deny))

    return ToolPolicy(allow=allow, deny=deny or None, profile=profile)


class ToolManager:
    """
    Enhanced ToolManager with session-locking, middleware, and fail-closed safety.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Any] = {}
        self._specs: Dict[str, ToolSpec] = {}
        self._handlers: Dict[str, Any] = {}
        self._lifecycle_overrides: Dict[str, str] = {}
        self._global_policy: ToolPolicy = ToolPolicy()
        self._tool_policies: Dict[str, ToolPolicy] = {}
        self._environment_policies: Dict[str, ToolPolicy] = {}
        self._role_policies: Dict[str, ToolPolicy] = {}
        self._group_policies: Dict[str, ToolPolicy] = {}
        self._session_policies: Dict[str, ToolPolicy] = {}
        self._before_hooks: List[Callable] = []
        self._middlewares: List[ToolMiddleware] = []
        self._usage_sinks: List[Any] = []
        self._safety_kernel: Any = None
        self._event_queue: Any = None
        self._pipeline = ToolPipeline(self)
        self._repo_root: Optional[str] = None
        self._session_locks: Dict[str, RLock] = {}
        self._global_session_guard = Lock()
        self._register_shell_aliases()
        
        # P5: Surgery Eighty-seven - Full Toolset Integration (OpenClaw Parity)
        from quentin.tools.network import net_inspect_port
        from quentin.tools.system import sys_top_snapshot
        self.register("net.inspect_port", net_inspect_port)
        self.register("sys.top_snapshot", sys_top_snapshot)
        
        self.add_middleware(AuthRotationMiddleware())

    def _get_session_lock(self, session_id: str) -> Any:
        # P5: Tier 0 Cross-Process Locking (Lanes)
        # Replaces local RLock with persistent file-based locks
        try:
            from quentin.infra.concurrency.session_registry import get_session_registry
            registry = get_session_registry(repo_root=self.repo_root or ".")
            return registry.acquire_lock(session_id)
        except Exception:
            # Fallback to local lock if registry fails
            with self._global_session_guard:
                if session_id not in self._session_locks:
                    self._session_locks[session_id] = RLock()
                return self._session_locks[session_id]

    def set_repo_root(self, root: str) -> None:
        self._repo_root = root
        # P5: Surgery Nine - Add Security Audit Middleware
        self.add_middleware(SecurityAuditMiddleware(root))

    @property
    def repo_root(self) -> str:
        return self._repo_root or "."

    def set_safety_kernel(self, kernel: Any) -> None:
        self._safety_kernel = kernel

    def set_event_queue(self, queue: Any) -> None:
        self._event_queue = queue

    def _emit_tool_execution_event(
        self,
        *,
        session_id: str,
        turn_id: str,
        event_type: str,
        phase: str,
        tool_name: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        queue = self._event_queue
        if queue is None:
            return
        event_payload = {"tool_name": str(tool_name or "")}
        if isinstance(payload, dict):
            event_payload.update(payload)
        try:
            queue.emit_brain_event(
                session_id=str(session_id or "default"),
                event_type=str(event_type or "tool_execution_update"),
                category="tool",
                phase=str(phase or "update"),
                source="tool_manager",
                payload=event_payload,
                turn_id=str(turn_id or ""),
            )
        except Exception:
            pass

    def add_before_hook(self, hook: Callable) -> None:
        self._before_hooks.append(hook)

    def add_middleware(self, middleware: ToolMiddleware) -> None:
        self._middlewares.append(middleware)

    def add_usage_sink(self, sink: Any) -> None:
        self._usage_sinks.append(sink)

    def get(self, name: str, default: Any = None) -> Any:
        """
        Dict-like helper used by some legacy call sites/tests.
        Returns a tool handler if registered, otherwise `default`.
        """
        handler, _ = self._get_handler(name)
        return handler if handler is not None else default

    def set_global_policy(self, policy: ToolPolicy) -> None:
        self._global_policy = policy

    def set_environment_policy(self, env: str, policy: ToolPolicy) -> None:
        self._environment_policies[env] = policy

    def set_role_policy(self, role: str, policy: ToolPolicy) -> None:
        self._role_policies[str(role)] = policy

    def set_group_policy(self, group: str, policy: ToolPolicy) -> None:
        self._group_policies[str(group)] = policy

    def set_session_policy(self, session_id: str, policy: ToolPolicy) -> None:
        self._session_policies[str(session_id)] = policy

    def set_tool_policy(self, tool_name: str, policy: ToolPolicy) -> None:
        self._tool_policies[str(tool_name)] = policy

    def get_tool_menu(self, *, context_metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        P5: Produces a ultra-compact tool menu for fast-model filtering.
        """
        lines = []
        result = self._pipeline.resolve(metadata=context_metadata)
        for name in result.tool_names:
            desc = str(result.tool_descriptions.get(name) or "Legacy or alias tool.")
            lines.append(f"- {name}: {desc[:60]}")
        return "\n".join(lines)

    def get_tool_summaries(
        self,
        *,
        max_words: int = 10,
        context_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """
        Return a compact {tool_name -> summary} mapping for planner/executor prompts.

        This is intentionally lossy and stable; it favors short descriptions to
        reduce tool hallucinations and context bloat.
        """
        summaries, _ = self._pipeline.build_summaries(
            metadata=context_metadata,
            max_words=int(max_words or 10),
        )
        return summaries

    def get_tool_schema_help(self, tool_name: str) -> Dict[str, Any]:
        """
        Return a stable dict describing a tool's schema and risk metadata.

        Used by planners/routers and unit tests.
        """
        spec = self._specs.get(tool_name)
        if spec is None:
            return {"status": "error", "error": f"tool not found: {tool_name}"}

        input_schema = normalize_tool_schema(spec.input_schema or {})
        input_schema = patch_tool_schema_for_claude_compatibility(input_schema)
        output_schema = normalize_tool_schema(spec.output_schema or {})
        return {
            "status": "ok",
            "tool_name": spec.name,
            "description": spec.description,
            "domain": getattr(spec, "domain", None),
            "kind": getattr(spec, "kind", None),
            "input_schema": input_schema,
            "output_schema": output_schema,
            "risk_level": getattr(spec, "risk_level", None),
            "lifecycle": getattr(spec, "lifecycle", None),
            "meta": dict(getattr(spec, "meta", None) or {}),
        }

    def register(self, name: str, tool: Any) -> None:
        """
        Legacy/Alias registration.
        """
        self._tools[name] = tool
        self._handlers[name] = tool

    def register_tool(self, spec: ToolSpec, handler: Any) -> None:
        self._specs[spec.name] = spec
        self._tools[spec.name] = handler
        self._handlers[spec.name] = handler

    def register_pack(self, pack: Any) -> None:
        """
        Registers all tools from a ToolPack instance.
        """
        from quentin.tools.packs.base import ToolPack
        if isinstance(pack, ToolPack):
            for spec, handler in pack.get_tools():
                self.register_tool(spec, handler)
        elif isinstance(pack, dict):
            # Legacy dict-based registration support
            for _, val in pack.items():
                spec, handler = val
                self.register_tool(spec, handler)
    def get_tool_names_by_domain(self, domain: str = "core") -> List[str]:
        """
        P5: Cognitive Filtering - Return only relevant tools for the active domain.
        Matches OpenClaw's scenario-based injection.
        """
        all_tools = self.list_tool_names()
        relevant = set()
        
        # 1. Core Survival Set (Always Visible)
        # Includes aliases like 'ls' and specific names like 'shell.run_command'
        core_keywords = ("fs.", "shell.", "sys.", "ls", "cat", "pwd", "grep", "find", "mkdir")
        for t in all_tools:
            if any(t.startswith(kw) or t == kw for kw in core_keywords):
                relevant.add(t)
        
        # 2. Domain-Specific Extensions
        domain = domain.lower().strip()
        domain_map = {
            "web": ("browser.", "web."),
            "mobile": ("adb.", "mobile."),
            "desktop": ("desktop.", "gui."),
            "memory": ("memory.",),
            "communication": ("slack.", "discord.", "telegram.", "whatsapp.", "sessions."),
            "ops": ("cron.", "session.", "sessions.", "sys.", "net."),
            "media": ("image.", "tts.", "vision."),
            "meta": ("agents.", "nodes.", "sessions."),
        }
        
        if domain in domain_map:
            prefixes = domain_map[domain]
            for t in all_tools:
                if t.startswith(prefixes): relevant.add(t)
        
        return sorted(list(relevant))

    def list_tool_names(self) -> List[str]:
        return sorted(list(set(list(self._handlers.keys()) + list(self._specs.keys()) + list(self._tools.keys()))))

    def get_restricted_copy(self, role_name: str) -> "ToolManager":
        """
        P5: Ported from OpenClaw's ToolRegistry.restrictByRole.
        Creates a new ToolManager instance with only handles allowed for the role.
        """
        from quentin.tools.role_profiles import RoleProfiles
        allowed_set = RoleProfiles.get_allowed_tools(role_name)
        
        logger.info(f"ToolManager: Creating restricted copy for role='{role_name}' ({len(allowed_set)} tools)")
        
        new_mgr = ToolManager()
        new_mgr._repo_root = self._repo_root
        new_mgr._safety_kernel = self._safety_kernel
        
        # Physically only copy allowed handles and specs
        for name in allowed_set:
            handler, canonical = self._get_handler(name)
            if handler:
                new_mgr._handlers[canonical] = handler
                if canonical in self._specs:
                    new_mgr._specs[canonical] = self._specs[canonical]
                if canonical in self._tools:
                    new_mgr._tools[canonical] = self._tools[canonical]
                    
        return new_mgr

    def _normalize_name(self, name: str) -> str:
        # P5: Aggressive normalization
        return "".join(filter(str.isalnum, name.lower()))

    def _get_handler(self, name: str) -> Tuple[Optional[Any], Optional[str]]:
        if name in self._handlers: return self._handlers[name], name
        norm_input = self._normalize_name(name)
        for h_name, handler in self._handlers.items():
            if self._normalize_name(h_name) == norm_input: return handler, h_name
        hallucination_map = {
            "read": "fs.read_file", "write": "fs.write_file", "run": "shell.run_command", "shell": "shell.run_command"
        }
        if norm_input in hallucination_map:
            target = hallucination_map[norm_input]
            return self._handlers.get(target), target

        # Lazy plugin reload: if enabled, scan extensions and retry once.
        if (os.getenv("QUENTIN_TOOL_PLUGINS_ENABLED", "") or "").strip().lower() in ("1", "true", "yes", "on") and (
            (os.getenv("QUENTIN_TOOL_PLUGINS_LAZY_RELOAD", "") or "").strip().lower() in ("1", "true", "yes", "on")
        ):
            try:
                from quentin.tools.plugin_loader import register_tool_plugins

                register_tool_plugins(tool_manager=self, repo_root=Path(self.repo_root))
                if name in self._handlers:
                    return self._handlers[name], name
                for h_name, handler in self._handlers.items():
                    if self._normalize_name(h_name) == norm_input:
                        return handler, h_name
            except Exception:
                pass
        return None, None

    def _register_shell_aliases(self) -> None:
        async def _shell_alias_handler(req: ToolCallRequest, ctx: ToolCallContext) -> ToolCallResult:
            command_name = req.tool_name
            payload = req.payload or {}
            command_str = ""
            if "command" in payload and isinstance(payload["command"], str):
                command_str = payload["command"]
            else:
                found_val = None
                for k in ["path", "file", "target", "dir", "pattern", "filepath", "src", "dest"]:
                    if k in payload and isinstance(payload[k], str):
                        found_val = shlex.quote(payload[k])
                        break
                if found_val:
                    command_str = f"{command_name} {found_val}"
                else:
                    all_strings = [shlex.quote(str(v)) for v in payload.values() if isinstance(v, (str, int)) and str(v) != command_name]
                    if all_strings:
                        command_str = f"{command_name} {' '.join(all_strings)}"
                    else:
                        command_str = command_name
            
            shell_handler = self._handlers.get("shell.run_command") or self._handlers.get("shell_run_command")
            if not shell_handler:
                return ToolCallResult(tool_name=command_name, success=False, error="Base shell tool not found")
            
            req.payload = {"command": command_str.strip()}
            return await shell_handler(req, ctx)

        for alias in ["ls", "grep", "cat", "mkdir", "rm", "cp", "mv", "touch", "chmod", "df", "du", "pwd"]:
            self._handlers[alias] = _shell_alias_handler

    def invoke(self, name: str, params: Optional[Dict[str, Any]] = None, ctx: Optional[ToolCallContext] = None) -> Any:
        """
        Sync wrapper for tool invocation (primarily used by unit tests and legacy call sites).

        Prefer `await call_tool()` inside async contexts.
        """
        params = params or {}
        ctx = ctx or ToolCallContext()

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            res = asyncio.run(self.call_tool(ToolCallRequest(tool_name=name, payload=params), ctx=ctx))
        else:
            raise RuntimeError("ToolManager.invoke() cannot be used inside an active event loop; use await call_tool().")

        if not res.success:
            raise RuntimeError(str(res.error or "tool failed"))
        return res.output

    def is_messaging_tool(self, tool_name: str) -> bool:
        """
        P5: Identifies if a tool is a 'messaging' tool (sends direct user replies).
        """
        if not tool_name:
            return False
        norm = tool_name.lower().strip()
        # Core messaging tools from OpenClaw parity
        if norm in ("sessions_send", "message", "telegram.send_message", "slack.post_message"):
            return True
        # Check domain/kind if available in specs
        spec = self._specs.get(tool_name)
        if spec:
            if getattr(spec, "domain", "") == "communication":
                return True
            if "messaging" in (spec.meta or {}).get("tags", []):
                return True
        return False

    async def call_tool(self, req: ToolCallRequest, ctx: Optional[ToolCallContext] = None) -> ToolCallResult:
        handler, canonical_name = self._get_handler(req.tool_name)
        if handler is None:
            # P5: Proactive discovery hint
            raise KeyError(f"tool not found: {req.tool_name}")

        tool_name = canonical_name
        params = normalize_tool_params(dict(req.payload or {}))
        ctx = ctx or ToolCallContext()
        if not isinstance(ctx.metadata, dict):
            ctx.metadata = {}
        md = ctx.metadata

        # P5: Surgery Fifty-two - Inverse Parameter Mapping (OpenClaw Parity)
        from quentin.tools.transformer_engine import SchemaTransformerEngine
        provider_id = str(md.get("provider", "generic")).lower()
        if provider_id in ("gemini", "google"):
            spec = self._specs.get(tool_name)
            if spec:
                logger.debug(f"ToolManager: Un-flattening params for {tool_name} (provider={provider_id})")
                params = SchemaTransformerEngine.unflatten_params(params, spec.input_schema or {})

        # P5: Surgery Sixty - Dynamic Latency Assignment (OpenClaw Parity)
        from quentin.infra.tools.latency_profile import LatencyProfile
        current_timeout = params.get("timeout_seconds") or params.get("timeout")
        params["timeout_seconds"] = LatencyProfile.get_timeout(tool_name, user_override=current_timeout)

        # P5: OpenClaw Parity - Parameter Sanitization
        from quentin.infra.tools.sanitizer import sanitizer
        try:
            params = sanitizer.sanitize(tool_name, params)
        except ValueError as e:
            # P5: Provide model-facing feedback for parameter errors
            return ToolCallResult(
                tool_name=tool_name, 
                success=False, 
                error=str(e),
                output={"status": "error", "error": str(e), "hint": "Check tool parameters and retry."}
            )
        except Exception as e:
            return ToolCallResult(tool_name=tool_name, success=False, error=f"Invalid parameters: {e}")

        # Respect cancellation (fail-fast) before any side effects.
        self._pipeline.ensure_not_cancelled(ctx.cancel_token)

        # Policy gate (fail-closed). This is independent from SafetyKernel.
        eff = resolve_effective_tool_policy(
            global_policy=self._global_policy,
            stacked=self._resolve_effective_policies(tool_name, ctx),
        )
        if not _is_allowed(tool_name, [eff]):
            raise PermissionError(f"tool denied by policy: {tool_name}")
        
        session_id = str(md.get("session_id") or "default")
        turn_id = str(md.get("turn_id") or md.get("task_id") or req.trace_id or "")
        session_lock = self._get_session_lock(session_id)
        self._emit_tool_execution_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="tool_execution_start",
            phase="start",
            tool_name=tool_name,
            payload={"trace_id": str(req.trace_id or ""), "auth_attempt": 0},
        )

        # P5: OpenClaw Parity - Silent Auth Rotation Loop
        MAX_AUTH_RETRIES = 2
        for auth_attempt in range(MAX_AUTH_RETRIES + 1):
            chain = self._build_middleware_chain() if self._middleware_pipeline_enabled() else None
            
            # 1. Before hooks/middleware
            current_params = dict(params)
            if chain is not None:
                current_params, _ = chain.run_before(tool_name=tool_name, params=current_params, ctx=ctx)
            else:
                for hook in self._before_hooks:
                    outcome = hook(tool_name, current_params, ctx)
                    if outcome.get("blocked"):
                        raise PermissionError(outcome.get("reason", "tool blocked by hook"))
                    current_params = outcome.get("params", current_params)

            # SafetyKernel guard (includes risk summarization/redaction).
            action_id = self._guard_tool_call_or_raise(tool_name=tool_name, params=current_params, ctx=ctx)
            
            # P5: Surgery Sixty-two - Mode Auto-degradation (OpenClaw Parity)
            from quentin.infra.security.sensitivity_classifier import SensitivityClassifier
            is_sensitive = SensitivityClassifier.should_restrict_execution(current_params)
            if is_sensitive:
                logger.warning(f"ToolManager: SENSITIVE PATH DETECTED in {tool_name}. Downgrading to Restricted Mode.")
                # We inject flags that downstream tools (like shell) can pick up to sandbox further
                current_params["_restricted_mode"] = True
                md["risk_level"] = "critical"
                self._emit_tool_execution_event(
                    session_id=session_id,
                    turn_id=turn_id,
                    event_type="tool_execution_update",
                    phase="update",
                    tool_name=tool_name,
                    payload={"auth_attempt": auth_attempt, "restricted_mode": True},
                )

            # P5: Surgery Fifty-seven - Speculative Dry Run (OpenClaw Parity)
            from quentin.tools.middleware.speculative_runner import SpeculativeRunner
            if SpeculativeRunner.supports_dry_run(tool_name):
                # Note: This assumes handler can be called synchronously for check or we need async adapter
                # For this surgery, we only support if handler is compatible.
                # In full OpenClaw, this is handled via tool-specific adapters.
                pass 

            # 2. Physical Execution
            with session_lock:
                try:
                    # P5: Dry Run Integration (Inline for now to leverage async handler access)
                    if SpeculativeRunner.supports_dry_run(tool_name) and not current_params.get("dry_run"):
                        # We need to construct a dry-run request
                        dry_req = ToolCallRequest(tool_name=tool_name, payload={**current_params, "dry_run": True}, trace_id=req.trace_id)
                        dry_res = _call_handler_with_optional_ctx(handler, dry_req, dry_req.payload, ctx)
                        if hasattr(dry_res, "__await__"):
                            dry_res = await dry_res
                        
                        dry_ok = False
                        if isinstance(dry_res, ToolCallResult): dry_ok = dry_res.success
                        elif isinstance(dry_res, dict): dry_ok = dry_res.get("status") == "ok"
                        
                        if not dry_ok:
                            msg = getattr(dry_res, "error", "") if hasattr(dry_res, "error") else str(dry_res)
                            logger.warning(f"ToolManager: Speculative Dry Run FAILED for {tool_name}. Blocking execution.")
                            self._emit_tool_execution_event(
                                session_id=session_id,
                                turn_id=turn_id,
                                event_type="tool_execution_end",
                                phase="end",
                                tool_name=tool_name,
                                payload={"success": False, "status": "dry_run_failed", "error": str(msg or "")[:800]},
                            )
                            return ToolCallResult(
                                tool_name=tool_name,
                                success=False,
                                error=f"dry_run_failed: The operation would fail. Reason: {msg}",
                                output={"hint": "Your patch/command is invalid. I blocked it to protect the file system. Please fix the input based on the dry-run error."}
                            )

                    req2 = ToolCallRequest(tool_name=tool_name, payload=dict(current_params), trace_id=req.trace_id, meta=dict(req.meta or {}))
                    exec_started = time.perf_counter()
                    res = _call_handler_with_optional_ctx(handler, req2, current_params, ctx)
                    if hasattr(res, "__await__"):
                        res = await res
                    
                    if isinstance(res, ToolCallResult):
                        result = res
                    else:
                        if isinstance(res, dict):
                            status = str(res.get("status") or "").strip().lower()
                            
                            # P5: Surgery Forty-eight - HITL Signal Handling (OpenClaw Parity)
                            if status == "requires_approval":
                                self._emit_tool_execution_event(
                                    session_id=session_id,
                                    turn_id=turn_id,
                                    event_type="tool_execution_end",
                                    phase="end",
                                    tool_name=tool_name,
                                    payload={"success": False, "status": "approval_required"},
                                )
                                return ToolCallResult(
                                    tool_name=tool_name,
                                    success=False,
                                    output=res, # Passthrough the full escalation request
                                    error="approval_required",
                                    meta={"requires_approval": True, "type": res.get("type")}
                                )

                            if status == "error":
                                err = str(res.get("error") or "tool_error")
                                result = ToolCallResult(
                                    tool_name=tool_name,
                                    success=False,
                                    output=sanitize_tool_output(res),
                                    error=err,
                                    meta={},
                                )
                            else:
                                result = ToolCallResult(tool_name=tool_name, success=True, output=sanitize_tool_output(res), meta={})
                        else:
                            result = ToolCallResult(tool_name=tool_name, success=True, output=sanitize_tool_output({"result": res}), meta={})

                    result.meta.setdefault("action_id", action_id)
                    
                    # P5: OpenClaw Parity - Messaging Tool Suppression Logic
                    if result.success and self.is_messaging_tool(tool_name):
                        result.meta.setdefault("direct_response_sent", True)
                    
                    # P5: OpenClaw Parity - Tool Metadata Extension (pty/elevated)
                    if isinstance(current_params, dict):
                        if current_params.get("pty") is True:
                            result.meta.setdefault("pty", True)
                        if current_params.get("elevated") is True:
                            result.meta.setdefault("elevated", True)

                    # 3. After hooks/middleware (This is where AuthRotation signals a retry)
                    if chain is not None:
                        try:
                            result = chain.run_after(tool_name=tool_name, params=current_params, result=result, ctx=ctx)
                        except Exception:
                            pass
                    
                    # P5: Surgery Three - Check for Auth Rotation Signal
                    if result.meta.get("requires_auth_rotation") and auth_attempt < MAX_AUTH_RETRIES:
                        logger.warning(f"ToolManager: Silent Auth Rotation Triggered (Attempt {auth_attempt+1})")
                        self._emit_tool_execution_event(
                            session_id=session_id,
                            turn_id=turn_id,
                            event_type="tool_execution_update",
                            phase="update",
                            tool_name=tool_name,
                            payload={"auth_attempt": auth_attempt + 1, "status": "auth_rotation_retry"},
                        )
                        # We continue the loop, which will re-run 'before' and 'execute' with new auth context
                        continue

                    self._maybe_wrap_untrusted_output(tool_name=tool_name, result=result)

                    self._pipeline.ensure_not_cancelled(ctx.cancel_token)

                    latency_ms = int(max(0.0, (time.perf_counter() - exec_started) * 1000.0))
                    result.meta.setdefault("latency_ms", latency_ms)

                    # Best-effort usage recording (e.g. tool knowledge writeback).
                    if self._usage_sinks:
                        tool_spec = self._specs.get(tool_name)
                        for sink in list(self._usage_sinks):
                            try:
                                record_fn = getattr(sink, "record", None)
                                if callable(record_fn):
                                    record_fn(
                                        tool_name=tool_name,
                                        arguments=dict(current_params or {}),
                                        result=result,
                                        success=bool(result.success),
                                        latency_ms=latency_ms,
                                        tool_spec=tool_spec,
                                    )
                            except Exception:
                                pass

                    # P3-Audit: Security Audit Logging
                    try:
                        from quentin.security.audit_schema import AuditEvent as SecurityAuditEvent
                        from quentin.kernel.audit import default_audit_logger
                        
                        sec_event = SecurityAuditEvent(
                            event_id=result.meta.get("action_id") or uuid.uuid4().hex,
                            actor=str((ctx.metadata or {}).get("actor") or "tool_manager"),
                            action=f"tool_call:{tool_name}",
                            resource=tool_name,
                            decision="allow" if result.success else "block",
                            reason=str(result.error or ""),
                            trace_id=str(req.trace_id or ""),
                            session_id=session_id,
                            metadata={"params": current_params, "output_keys": list((result.output or {}).keys())}
                        )
                        default_audit_logger().append(sec_event)
                    except Exception:
                        pass

                    self._emit_tool_execution_event(
                        session_id=session_id,
                        turn_id=turn_id,
                        event_type="tool_execution_end",
                        phase="end",
                        tool_name=tool_name,
                        payload={
                            "success": bool(result.success),
                            "status": "ok" if result.success else "error",
                            "error": str(result.error or "")[:800],
                            "latency_ms": int(result.meta.get("latency_ms") or 0),
                            "auth_attempt": auth_attempt,
                        },
                    )
                    return result
                except (PermissionError, CancelledError):
                    self._emit_tool_execution_event(
                        session_id=session_id,
                        turn_id=turn_id,
                        event_type="tool_execution_end",
                        phase="end",
                        tool_name=tool_name,
                        payload={"success": False, "status": "cancelled_or_denied"},
                    )
                    raise
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).exception(f"Async tool {tool_name} failed")
                    
                    # P5: Surgery Forty-seven - Semantic Hinting (OpenClaw Parity)
                    from quentin.infra.tools.sanitizer import SemanticHintGenerator
                    enriched = SemanticHintGenerator.enrich_error(tool_name, e)
                    
                    # Record the failure event
                    try:
                        self._record_trace("tool_error", {
                            "tool": tool_name,
                            "error": enriched["error"],
                            "hint": enriched.get("hint")
                        })
                    except Exception: pass
                    self._emit_tool_execution_event(
                        session_id=session_id,
                        turn_id=turn_id,
                        event_type="tool_execution_end",
                        phase="end",
                        tool_name=tool_name,
                        payload={"success": False, "status": "exception", "error": str(enriched["error"])[:800]},
                    )
                    
                    return ToolCallResult(
                        tool_name=tool_name, 
                        success=False, 
                        error=enriched["error"],
                        output=enriched # Includes the hint for the LLM
                    )
        
        # Fallback return (should not be reached normally due to inner return)
        self._emit_tool_execution_event(
            session_id=session_id,
            turn_id=turn_id,
            event_type="tool_execution_end",
            phase="end",
            tool_name=tool_name,
            payload={"success": False, "status": "auth_rotation_failed"},
        )
        return ToolCallResult(tool_name=tool_name, success=False, error="Auth rotation failed after max retries")

    def _guard_tool_call_or_raise(self, *, tool_name: str, params: Dict[str, Any], ctx: ToolCallContext) -> str:
        from quentin.kernel.safety import get_safety_kernel
        kernel = self._safety_kernel or get_safety_kernel()
        if kernel is None:
            critical_prefixes = {"fs.", "shell.", "sys.", "exec."}
            if any(tool_name.startswith(p) for p in critical_prefixes):
                raise PermissionError(f"SafetyKernel UNAVAILABLE. Tool {tool_name} blocked (fail-closed).")
            return f"unguarded_{uuid.uuid4().hex}"
        
        from quentin.kernel.policy import ActionRequest
        md = ctx.metadata or {}

        # Risk summarization & redaction for sensitive args.
        risk_summary: Dict[str, Any] = {}
        safe_meta: Dict[str, Any] = {"tool_name": tool_name}
        approval_context: Dict[str, Any] = {}

        if tool_name in ("shell.run_command", "shell_run_command") or tool_name.startswith("shell."):
            cmd = params.get("command")
            head = None
            flags: List[str] = []
            if isinstance(cmd, str) and cmd.strip():
                try:
                    toks = shlex.split(cmd)
                except Exception:
                    toks = cmd.strip().split()
                head = toks[0] if toks else None
                flags = [t for t in toks[1:] if isinstance(t, str) and t.startswith("-")]
            is_destructive = bool(head in {"rm", "dd", "mkfs", "shutdown", "reboot"})
            risk_summary.update(
                {
                    "command_head": head,
                    "command_flags": flags[:16],
                    "is_destructive_candidate": is_destructive,
                }
            )
            if head:
                safe_meta["command_head"] = head
            # Full command text is intentionally NOT logged by default. It is only
            # attached when HITL approval is enabled.
        else:
            # Common "target path" summaries (avoid including full content/diffs).
            for key in ("path", "target_path", "filepath", "file", "src", "dest"):
                if key in params and isinstance(params.get(key), str):
                    risk_summary.update({"target_path": params.get(key), "target_path_key": key})
                    # Only attached when HITL approval is enabled.
                    break

        safe_meta["risk_summary"] = risk_summary

        # Optional HITL (default OFF): request approval for risky tool calls.
        approval_enabled = (os.getenv("QUENTIN_APPROVAL_GATE", "0") or "").strip().lower() in ("1", "true", "yes", "on")
        if approval_enabled:
            if tool_name.startswith("shell."):
                readonly = {"ls", "pwd", "cat", "rg", "grep", "find", "which", "echo"}
                head = str(risk_summary.get("command_head") or "").strip().split("/")[-1].lower()
                if head and head not in readonly:
                    safe_meta["approval_required"] = True
                    safe_meta["approval_reason"] = f"shell command requires approval: {head}"
                    cmd = params.get("command")
                    if isinstance(cmd, str) and cmd.strip():
                        approval_context["command"] = cmd.strip()[:2000]
                        approval_context["command_head"] = risk_summary.get("command_head")
                        approval_context["command_flags"] = list(risk_summary.get("command_flags") or [])[:32]
            if tool_name in ("fs.write_file", "fs.search_replace"):
                if (os.getenv("QUENTIN_APPROVAL_FS_WRITE", "0") or "").strip().lower() in ("1", "true", "yes", "on"):
                    safe_meta["approval_required"] = True
                    safe_meta["approval_reason"] = f"{tool_name} requires approval"
                    for key in ("path", "target_path", "filepath", "file", "src", "dest"):
                        if key in params and isinstance(params.get(key), str):
                            approval_context["target_path"] = params.get(key)
                            approval_context["target_path_key"] = key
                            break

            if approval_context:
                safe_meta["approval_context"] = approval_context

        action = ActionRequest.new(
            actor=str(md.get("actor") or "tool_manager"),
            action_type="tool_call",
            domain=str(md.get("domain") or "core"),
            environment=str(md.get("environment") or "sandbox"),
            risk_level=str(md.get("risk_level") or "medium"),
            description=f"tool_call:{tool_name}",
            metadata=safe_meta,
        )
        guard = kernel.guard_action(action)
        allow = bool(getattr(guard, "allow", False))
        reason = str(getattr(guard, "reason", "") or "")
        if not allow:
            raise PermissionError(f"safety_kernel denied {tool_name}: {reason or 'denied'}")
        return action.action_id

    def _maybe_wrap_untrusted_output(self, *, tool_name: str, result: ToolCallResult) -> None:
        if not result.success or not isinstance(result.output, dict):
            return
        spec = self._specs.get(tool_name)
        if spec and (spec.meta or {}).get("output_trust") == "untrusted":
            raw_text = str(result.output.get("result") or json.dumps(result.output))
            warning = "SECURITY NOTICE: EXTERNAL UNTRUSTED CONTENT\n"
            wrapped = f"{warning}<<<EXTERNAL_UNTRUSTED_CONTENT>>>\n{raw_text}\n<<<END_EXTERNAL_UNTRUSTED_CONTENT>>>"
            result.output["_untrusted_wrapped_text"] = wrapped
            result.meta.setdefault("untrusted_output_wrapped", True)
            # Preserve structured outputs for programmatic use; only overwrite when result is plain text.
            if isinstance(result.output.get("result"), str):
                result.output["result"] = wrapped

    def _middleware_pipeline_enabled(self) -> bool:
        raw = (os.getenv("QUENTIN_TOOL_MIDDLEWARE_PIPELINE", "0") or "").strip().lower()
        return raw in ("1", "true", "yes", "on")

    def _build_middleware_chain(self) -> ToolMiddlewareChain:
        ordered = ToolMiddlewareChain.order(self._middlewares)

        before_hooks = list(self._before_hooks)

        class _LegacyBeforeHooksShim:
            id = "legacy_before_hooks"
            priority = -10

            def before(self, *, tool_name: str, params: Dict[str, Any], ctx: ToolCallContext) -> BeforeOutcome:
                cur = dict(params or {})
                for hook in before_hooks:
                    outcome = hook(tool_name, cur, ctx)
                    if outcome.get("blocked"):
                        return BeforeOutcome(
                            params=cur,
                            blocked=True,
                            reason=str(outcome.get("reason") or "tool blocked by hook"),
                            ctx_metadata_delta={},
                        )
                    cur = outcome.get("params", cur)
                return BeforeOutcome(params=cur, blocked=False, reason="", ctx_metadata_delta={})

            def after(self, *, tool_name: str, params: Dict[str, Any], result: ToolCallResult, ctx: ToolCallContext) -> AfterOutcome:
                return AfterOutcome(result=result, ctx_metadata_delta={})

        ordered.append(_LegacyBeforeHooksShim())
        return ToolMiddlewareChain(ordered)

    def _get_effective_lifecycle(self, tool_name: str) -> str:
        return self._lifecycle_overrides.get(tool_name, "stable")

    def _resolve_effective_policies(self, tool_name: str, ctx: ToolCallContext) -> List[ToolPolicy]:
        md = ctx.metadata or {}
        stacked: List[ToolPolicy] = []

        env = md.get("environment")
        if isinstance(env, str) and env in self._environment_policies:
            stacked.append(self._environment_policies[env])

        role = md.get("role")
        if isinstance(role, str) and role in self._role_policies:
            stacked.append(self._role_policies[role])

        group = md.get("group")
        if isinstance(group, str) and group in self._group_policies:
            stacked.append(self._group_policies[group])
        groups = md.get("groups")
        if isinstance(groups, list):
            for g in groups:
                if isinstance(g, str) and g in self._group_policies:
                    stacked.append(self._group_policies[g])

        session_id = md.get("session_id")
        if isinstance(session_id, str) and session_id in self._session_policies:
            stacked.append(self._session_policies[session_id])

        if tool_name in self._tool_policies:
            stacked.append(self._tool_policies[tool_name])

        if ctx.policies:
            stacked.extend([p for p in ctx.policies if isinstance(p, ToolPolicy)])

        return stacked

def _call_handler_with_optional_ctx(handler: Callable, req: ToolCallRequest, params: Dict[str, Any], ctx: ToolCallContext):
    """
    Supports both handler styles:
    - handler(req) / handler(req, ctx) / handler(req, *, ctx=...)
    - handler(params) / handler(params, ctx) / handler(params, *, ctx=...) / handler(params, *, context=...)
    """
    try:
        sig = inspect.signature(handler)
    except Exception:
        return handler(params)

    positional = [
        p
        for p in sig.parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    first = positional[0] if positional else None
    wants_req = False
    if first is not None:
        try:
            from quentin.tools.schemas import ToolCallRequest as _TCR

            if first.annotation is _TCR:
                wants_req = True
            ann = first.annotation
            if not wants_req and isinstance(ann, str) and ("ToolCallRequest" in ann):
                wants_req = True
        except Exception:
            pass
        # Back-compat: some handlers accept the full ToolCallRequest but don't annotate.
        # Treat `request` (not `req`) as the signal for that style to avoid breaking the
        # common dict-style signature `handler(req: Dict[str, Any], ctx=...)`.
        if not wants_req and first.name == "request" and first.annotation is inspect._empty:
            wants_req = True
        if not wants_req and first.name == "req":
            ann = first.annotation
            if ann is inspect._empty or (isinstance(ann, str) and ("ToolCallRequest" in ann)):
                wants_req = True

    arg0 = req if wants_req else params
    if "ctx" in sig.parameters:
        return handler(arg0, ctx=ctx)
    if "context" in sig.parameters:
        return handler(arg0, context=ctx)
    if len(positional) >= 2:
        return handler(arg0, ctx)
    return handler(arg0)

def _call_with_optional_ctx(fn: Callable, params: Dict, ctx: ToolCallContext):
    sig = inspect.signature(fn)
    if "ctx" in sig.parameters:
        return fn(params, ctx=ctx)
    return fn(params)

_TOOL_GROUPS = {
    "@core": ["ls", "pwd", "shell.run_command", "fs.get_write_policy"],
    "@file": ["fs.read_file", "fs.write_file", "fs.search_replace", "ls", "mkdir", "cat", "touch"],
    "@danger": ["shell.run_command", "rm", "chmod"],
}

def _expand_groups(patterns: List[str]) -> List[str]:
    expanded = []
    for p in patterns:
        if p.startswith("@") and p in _TOOL_GROUPS:
            expanded.extend(_TOOL_GROUPS[p])
        else:
            expanded.append(p)
    return expanded

def _is_allowed(name: str, policies: List[ToolPolicy]) -> bool:
    deny: List[str] = []
    allow: List[str] = []
    has_allow = False

    for p in policies:
        if p is None:
            continue
        if p.deny:
            deny.extend(_expand_groups([str(x) for x in p.deny if x]))
        if p.allow:
            has_allow = True
            allow.extend(_expand_groups([str(x) for x in p.allow if x]))

    for pat in deny:
        if fnmatch.fnmatch(name, pat) or pat == "*":
            return False

    if not has_allow:
        return True
    
    return any(fnmatch.fnmatch(name, pat) or pat == "*" for pat in allow)
