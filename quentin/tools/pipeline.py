from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from quentin.tools.summary_map import build_tool_summary_map


@dataclass
class ToolPipelineContext:
    session_id: str = "default"
    domain: str = "core"
    environment: str = "sandbox"
    channel: str = ""
    provider: str = "generic"
    role: str = ""
    group: str = ""
    groups: List[str] = field(default_factory=list)


@dataclass
class ToolPipelineResult:
    stage_order: List[str]
    tool_names: List[str]
    tool_descriptions: Dict[str, str]
    schema_dialect: str


class ToolPipeline:
    """
    Explicit 7-stage tool pipeline:
    base tools -> sandbox overrides -> domain/channel tools -> policy filter
    -> schema dialect -> cancellation wrapper.
    """

    STAGE_ORDER = [
        "base_tools",
        "sandbox_overrides",
        "domain_channel_tools",
        "policy_filter",
        "schema_dialect",
        "cancellation_wrapper",
    ]

    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self._sandbox_include: set[str] = set()
        self._sandbox_exclude: set[str] = set()

    def set_sandbox_overrides(
        self,
        *,
        include: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None,
    ) -> None:
        self._sandbox_include = {str(x).strip() for x in (include or []) if str(x).strip()}
        self._sandbox_exclude = {str(x).strip() for x in (exclude or []) if str(x).strip()}

    @staticmethod
    def _ctx_from_metadata(metadata: Optional[Dict[str, Any]]) -> ToolPipelineContext:
        md = dict(metadata or {})
        return ToolPipelineContext(
            session_id=str(md.get("session_id") or "default"),
            domain=str(md.get("domain") or "core"),
            environment=str(md.get("environment") or "sandbox"),
            channel=str(md.get("channel") or md.get("gateway_channel") or ""),
            provider=str(md.get("provider") or "generic"),
            role=str(md.get("role") or ""),
            group=str(md.get("group") or ""),
            groups=[str(x) for x in (md.get("groups") or []) if str(x).strip()] if isinstance(md.get("groups"), list) else [],
        )

    def _base_tools(self) -> List[str]:
        try:
            names = list(self.manager.get_tool_names_by_domain("core") or [])
            if names:
                return sorted(set([str(x) for x in names if str(x).strip()]))
        except Exception:
            pass
        return sorted(set([str(x) for x in (self.manager.list_tool_names() or []) if str(x).strip()]))

    def _apply_sandbox_overrides(self, names: List[str], *, ctx: ToolPipelineContext) -> List[str]:
        out = list(names)
        if str(ctx.environment).strip().lower() != "sandbox":
            return out
        if self._sandbox_exclude:
            out = [n for n in out if n not in self._sandbox_exclude]
        if self._sandbox_include:
            out.extend([n for n in self._sandbox_include if n])
        return sorted(set(out))

    def _domain_channel_tools(self, names: List[str], *, ctx: ToolPipelineContext) -> List[str]:
        out = set(names)
        domain = str(ctx.domain or "").strip().lower()
        if domain:
            try:
                out.update(self.manager.get_tool_names_by_domain(domain) or [])
            except Exception:
                pass
        channel = str(ctx.channel or "").strip().lower()
        if channel:
            prefixes = {
                "discord": ("discord.", "channel.", "sessions."),
                "slack": ("slack.", "channel.", "sessions."),
                "telegram": ("telegram.", "channel.", "sessions."),
                "whatsapp": ("whatsapp.", "channel.", "sessions."),
                "openclaw": ("channel.", "sessions."),
            }.get(channel, ("channel.", "sessions."))
            for name in (self.manager.list_tool_names() or []):
                n = str(name or "")
                if n.startswith(prefixes):
                    out.add(n)
        return sorted(set([str(x) for x in out if str(x).strip()]))

    def _policy_filter(self, names: List[str], *, ctx: ToolPipelineContext) -> List[str]:
        try:
            from quentin.tools.manager import ToolCallContext, resolve_effective_tool_policy, _is_allowed

            tool_ctx = ToolCallContext(
                metadata={
                    "session_id": ctx.session_id,
                    "environment": ctx.environment,
                    "domain": ctx.domain,
                    "role": ctx.role,
                    "group": ctx.group,
                    "groups": list(ctx.groups),
                }
            )
            out: List[str] = []
            for name in names:
                eff = resolve_effective_tool_policy(
                    global_policy=self.manager._global_policy,
                    stacked=self.manager._resolve_effective_policies(name, tool_ctx),
                )
                if _is_allowed(name, [eff]):
                    out.append(name)
            return out
        except Exception:
            return names

    @staticmethod
    def ensure_not_cancelled(cancel_token: Any) -> None:
        if cancel_token is None:
            return
        try:
            cancel_token.raise_if_cancelled()
        except Exception:
            raise

    @staticmethod
    def _schema_dialect(provider: str) -> str:
        p = str(provider or "").strip().lower()
        if p in {"gemini", "google"}:
            return "gemini"
        if p in {"claude", "anthropic"}:
            return "claude"
        if p in {"openai", "gpt"}:
            return "openai"
        return "generic"

    def resolve(self, *, metadata: Optional[Dict[str, Any]] = None) -> ToolPipelineResult:
        ctx = self._ctx_from_metadata(metadata)
        names = self._base_tools()
        names = self._apply_sandbox_overrides(names, ctx=ctx)
        names = self._domain_channel_tools(names, ctx=ctx)
        names = self._policy_filter(names, ctx=ctx)
        dialect = self._schema_dialect(ctx.provider)

        desc: Dict[str, str] = {}
        for name in names:
            spec = (self.manager._specs or {}).get(name)
            if spec is not None:
                desc[name] = str(getattr(spec, "description", "") or "")
            else:
                desc[name] = "Legacy or alias tool."
        return ToolPipelineResult(
            stage_order=list(self.STAGE_ORDER),
            tool_names=names,
            tool_descriptions=desc,
            schema_dialect=dialect,
        )

    def build_summaries(
        self,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        max_words: int = 10,
    ) -> Tuple[Dict[str, str], ToolPipelineResult]:
        result = self.resolve(metadata=metadata)
        summaries = build_tool_summary_map(
            tool_descriptions=result.tool_descriptions,
            max_words=int(max_words or 10),
        )
        return summaries, result
