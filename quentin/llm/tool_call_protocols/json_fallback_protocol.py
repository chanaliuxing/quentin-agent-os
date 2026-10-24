from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import logging
import re

from quentin.llm.tool_call_protocols.base import ToolCallProtocol, ProtocolDecision
from quentin.llm.client import call_llm

logger = logging.getLogger(__name__)

class JsonFallbackProtocol(ToolCallProtocol):
    """
    Protocol that parses JSON from model text output.
    Used for models that don't support native tool calling.
    """
    @property
    def id(self) -> str:
        return "json_fallback"

    @property
    def priority(self) -> int:
        return 50

    def supports(self, provider: str, model_name: str, config: Any) -> bool:
        # Fallback protocol usually supports everything as a last resort
        return True

    async def next_action(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: List[Dict[str, Any]],
        config: Any,
        context: Dict[str, Any],
    ) -> ProtocolDecision:
        from quentin.infra.concurrency.cancellation import CancellationToken
        cancel_token = context.get("cancel_token")

        try:
            out_raw = call_llm(
                config,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                actor="executor",
                domain=str(context.get("domain", "core")),
                environment=str(context.get("environment", "sandbox")),
                risk_level=str(context.get("risk_level", "medium")),
                action_metadata={
                    "component": "executor",
                    "step_id": context.get("current_step_id"),
                    "iteration": context.get("iteration"),
                    "protocol": self.id,
                },
                provider=getattr(config, "provider", None),
                model_name=getattr(config, "name", None),
                cancel_token=cancel_token if isinstance(cancel_token, CancellationToken) else None,
            )
            
            parsed = self._robust_json_parse(out_raw)
            if not isinstance(parsed, dict):
                return ProtocolDecision(
                    kind="final",
                    content=out_raw,
                    meta={"protocol": self.id, "parse_failed": True}
                )

            status = str(parsed.get("status") or "ok").lower()
            if status == "error":
                return ProtocolDecision(
                    kind="error",
                    error=parsed.get("error") or "model_reported_error",
                    content=parsed.get("result"),
                    meta={"raw_parsed": parsed, "protocol": self.id}
                )

            tool_call = parsed.get("call_tool")
            normalized_tool_calls = []
            if isinstance(tool_call, dict):
                tc = self._normalize_json_tool_call(tool_call)
                if tc:
                    normalized_tool_calls.append(tc)

            return ProtocolDecision(
                kind="tool_call" if normalized_tool_calls else "final",
                tool_calls=normalized_tool_calls,
                content=parsed.get("result") or out_raw if not normalized_tool_calls else None,
                meta={"raw_parsed": parsed, "protocol": self.id}
            )

        except Exception as e:
            logger.warning(f"JsonFallbackProtocol failed: {e}")
            return ProtocolDecision(
                kind="error",
                error=str(e),
                meta={"protocol": self.id}
            )

    def _robust_json_parse(self, text: str) -> Any:
        """
        Extracted from Executor._robust_json_parse
        """
        s = str(text or "").strip()
        # Remove verbose "thinking" sections that often wrap/precede JSON.
        s = re.sub(r"<think(?:ing)?\b[^>]*>[\s\S]*?</think(?:ing)?>", "", s, flags=re.IGNORECASE)
        s = re.sub(r"<final\b[^>]*>", "", s, flags=re.IGNORECASE)
        s = re.sub(r"</final>", "", s, flags=re.IGNORECASE)
        # Clean markdown markers
        if s.startswith("```"):
            s = re.sub(r"^```(json)?", "", s, flags=re.IGNORECASE)
            s = re.sub(r"```$", "", s).strip()

        # 1. Try simple parse
        try:
            return json.loads(s)
        except:
            pass
            
        # 2. Extract first { to last }
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1:
            s = s[start : end + 1]
            
        # 3. Handle unescaped backslashes
        try:
            return json.loads(s)
        except json.JSONDecodeError as je:
            if r"Invalid \escape" in str(je):
                s_fixed = s.replace("\\", "\\\\")
                s_fixed = s_fixed.replace('\\\\"', '\\"') 
                try:
                    return json.loads(s_fixed)
                except: pass

        # 4. Final attempt: Remove trailing commas
        s = re.sub(r",\s*([\]\}])", r"\1", s)
        try:
            return json.loads(s)
        except Exception:
            return None

    def _normalize_json_tool_call(self, tool_call: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(tool_call, dict):
            return None
        raw_name = (
            tool_call.get("tool_name")
            or tool_call.get("name")
            or tool_call.get("tool")
            or tool_call.get("tool_id")
            or tool_call.get("id")
        )
        name = str(raw_name or "").strip()
        alias_map = {
            "shell_run_command": "shell.run_command",
            "fs_write_file": "fs.write_file",
            "fs_read_file": "fs.read_file",
            "fs_search_replace": "fs.search_replace",
            "fs_list_dir": "fs.list_dir",
            "fs_mkdir": "fs.mkdir",
            "fs_exists": "fs.exists",
        }
        if name:
            name = alias_map.get(name.strip().lower(), name.strip())

        args = tool_call.get("args", tool_call.get("arguments"))
        if isinstance(args, str):
            parsed = self._robust_json_parse(args)
            args = parsed if isinstance(parsed, dict) else {}
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return None
        if name and not args:
            if name == "shell.run_command":
                command = tool_call.get("command")
                if command is not None:
                    args = {
                        "command": command,
                        **(
                            {"timeout_seconds": tool_call.get("timeout_seconds")}
                            if tool_call.get("timeout_seconds") is not None
                            else {}
                        ),
                        **(
                            {"yield_seconds": tool_call.get("yield_seconds")}
                            if tool_call.get("yield_seconds") is not None
                            else {}
                        ),
                    }
            elif name == "fs.write_file":
                path = tool_call.get("path", tool_call.get("file_path"))
                content = tool_call.get("content")
                if path is not None or content is not None:
                    args = {
                        **({"path": path} if path is not None else {}),
                        **({"content": content} if content is not None else {}),
                        **({"mode": tool_call.get("mode")} if tool_call.get("mode") is not None else {}),
                    }
            elif name in {"fs.read_file", "fs.exists", "fs.mkdir", "ls", "cat"}:
                path = tool_call.get("path", tool_call.get("file_path"))
                if path is not None:
                    args = {"path": path}
            elif name in {"grep", "fs.search_replace"}:
                path = tool_call.get("path", tool_call.get("file_path"))
                pattern = tool_call.get("pattern")
                replacement = tool_call.get("replacement")
                synthesized: Dict[str, Any] = {}
                if path is not None:
                    synthesized["path"] = path
                if pattern is not None:
                    synthesized["pattern"] = pattern
                if replacement is not None:
                    synthesized["replacement"] = replacement
                if synthesized:
                    args = synthesized
        if not name or not isinstance(args, dict):
            return None
        return {"tool_name": name, "args": args}
