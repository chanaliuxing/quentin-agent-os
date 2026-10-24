from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Tuple, Protocol

import json

from quentin.config.mcp_security import load_mcp_security
from quentin.governance.tool_council import ToolCandidate, ToolGovernanceDecision, ToolGovernanceGate
from quentin.tools.learning.tool_learning import ToolLearningConfig, ToolLearningModule
from quentin.tools.providers.base import ProviderReport, ToolProvider
from quentin.tools.schemas import ToolKind, ToolSpec


@dataclass(frozen=True)
class MCPToolDescriptor:
    server_id: str
    transport: str
    uri: Optional[str]
    auth_token: Optional[str]
    tool_name: str
    description: str
    signature: str
    risk_level: str
    category: Optional[str] = None
    schema: Dict[str, Any] | None = None
    examples: List[Dict[str, Any]] | None = None


def _load_registry_index(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _normalize_risk_level(raw: Any) -> str:
    v = str(raw or "medium").strip().lower()
    if v not in {"low", "medium", "high", "critical"}:
        return "medium"
    return v


def _risk_rank(risk: str) -> int:
    r = str(risk or "medium").strip().lower()
    if r == "low":
        return 1
    if r == "medium":
        return 2
    if r == "high":
        return 3
    if r == "critical":
        return 4
    return 2


def _iter_tools(registry_index: List[Dict[str, Any]]) -> List[MCPToolDescriptor]:
    out: List[MCPToolDescriptor] = []
    for entry in registry_index or []:
        if not isinstance(entry, dict):
            continue
        server_id = str(entry.get("server_id") or entry.get("name") or "").strip() or "unknown-server"
        transport = str(entry.get("transport") or "stdio").strip() or "stdio"
        uri = entry.get("uri")
        uri_s = str(uri).strip() if uri is not None else None
        auth_token = entry.get("auth_token")
        auth_s = str(auth_token).strip() if auth_token is not None else None
        tools = entry.get("tools") or []
        if not isinstance(tools, list):
            continue
        for t in tools:
            if not isinstance(t, dict):
                continue
            tool_name = str(t.get("name") or t.get("tool_id") or "").strip()
            if not tool_name:
                continue
            out.append(
                MCPToolDescriptor(
                    server_id=server_id,
                    transport=transport,
                    uri=uri_s,
                    auth_token=auth_s,
                    tool_name=tool_name,
                    description=str(t.get("description") or "").strip(),
                    signature=str(t.get("signature") or tool_name).strip(),
                    risk_level=_normalize_risk_level(t.get("risk_level")),
                    category=(str(t.get("category")).strip() if t.get("category") is not None else None),
                    schema=(t.get("schema") if isinstance(t.get("schema"), dict) else None),
                    examples=(t.get("examples") if isinstance(t.get("examples"), list) else None),
                )
            )
    return out


class _InvokeResult(Protocol):
    success: bool
    output: Any
    error: Optional[str]
    latency_ms: int


class _MCPBackend(Protocol):
    def invoke(self, *, server: Any, tool_name: str, arguments: Dict[str, Any]) -> _InvokeResult: ...


def _default_backend_loader() -> Tuple[_MCPBackend, Any]:
    from meta_agent.self_programming.mcp_integration.invoker import MCPToolInvoker
    from meta_agent.self_programming.mcp_integration.types import ServerDescriptor

    return MCPToolInvoker(), ServerDescriptor


def _whitelist_matches(*, whitelist: List[str], server_id: str, tool_name: str) -> bool:
    """
    Accept a few simple whitelist forms:
    - "server_id"
    - "server_id/tool_name"
    - "mcp.server_id.tool_name"
    """
    if not whitelist:
        return False
    s = str(server_id or "").strip()
    t = str(tool_name or "").strip()
    if not s or not t:
        return False
    forms = {s, f"{s}/{t}", f"mcp.{s}.{t}"}
    for item in whitelist:
        token = str(item or "").strip()
        if token in forms:
            return True
    return False


class MCPToolProvider(ToolProvider):
    provider_id = "mcp"

    def __init__(
        self,
        *,
        registry_path: str | Path = "config/mcp_registry.json",
        backend_loader: Optional[Callable[[], Tuple[_MCPBackend, Any]]] = None,
        tool_governance_gate: Optional[ToolGovernanceGate] = None,
    ) -> None:
        self.registry_path = Path(registry_path)
        self._backend_loader = backend_loader
        self._tool_governance_gate = tool_governance_gate

    def register(self, *, tool_manager: Any, repo_root: str) -> ProviderReport:
        cfg = load_mcp_security(repo_root)
        if not cfg.enabled:
            return ProviderReport(provider_id=self.provider_id, enabled=False, registered_tools=[], errors=[])

        rr = Path(repo_root).resolve()
        reg_path = self.registry_path
        if not reg_path.is_absolute():
            reg_path = (rr / reg_path).resolve()

        registry_index = _load_registry_index(reg_path)
        tools = _iter_tools(registry_index)
        registered: List[str] = []
        errors: List[Dict[str, Any]] = []

        # Static prescreen: if auto-install is disabled, only allow explicit whitelist.
        # Also: dangerous categories require explicit whitelist (even if auto-install is enabled).
        allowed: List[MCPToolDescriptor] = []
        for td in tools:
            is_dangerous = bool(td.category) and str(td.category).strip().lower() in {
                str(x).strip().lower() for x in (cfg.dangerous_categories or [])
            }
            is_whitelisted = _whitelist_matches(
                whitelist=list(cfg.whitelist or []),
                server_id=td.server_id,
                tool_name=td.tool_name,
            )
            if is_dangerous and not is_whitelisted:
                continue
            if (not cfg.allow_auto_tool_install) and (not is_whitelisted):
                continue
            allowed.append(td)

        if not allowed:
            return ProviderReport(provider_id=self.provider_id, enabled=True, registered_tools=[], errors=[])

        # Optional governance gate (pluggable). If enabled, require a non-reject decision.
        gated: List[MCPToolDescriptor] = []
        gate = self._tool_governance_gate
        if cfg.enable_tool_governance and gate is None:
            # No gate provided; be conservative.
            return ProviderReport(
                provider_id=self.provider_id,
                enabled=True,
                registered_tools=[],
                errors=[{"error": "tool_governance_enabled_but_no_gate"}],
            )

        for td in allowed:
            if cfg.enable_tool_governance and gate is not None:
                decision: ToolGovernanceDecision
                try:
                    decision = gate.decide(
                        candidate=ToolCandidate(
                            tool_id=f"mcp.{td.server_id}.{td.tool_name}",
                            signature=td.signature,
                            description=td.description,
                            categories=[td.category] if td.category else [],
                            source="mcp_registry",
                            meta={"server_id": td.server_id, "transport": td.transport},
                        ),
                        context={"repo_root": str(rr), "provider": "mcp"},
                    )
                except Exception as e:  # noqa: BLE001
                    errors.append({"tool": f"mcp.{td.server_id}.{td.tool_name}", "error": f"tool_governance_failed:{e}"})
                    continue
                if decision.verdict == "reject":
                    continue
            gated.append(td)

        if not gated:
            return ProviderReport(provider_id=self.provider_id, enabled=True, registered_tools=[], errors=errors)

        backend_loader = self._backend_loader or _default_backend_loader
        try:
            invoker, ServerDescriptor = backend_loader()
        except Exception as e:  # noqa: BLE001
            return ProviderReport(
                provider_id=self.provider_id,
                enabled=True,
                registered_tools=[],
                errors=[{"error": f"mcp_backend_unavailable: {e}"}],
            )

        for td in gated:
            # Naming: mcp.<server_id>.<tool_name>
            tool_spec_name = f"mcp.{td.server_id}.{td.tool_name}"
            risk = td.risk_level
            is_dangerous = bool(td.category) and str(td.category).strip().lower() in {
                str(x).strip().lower() for x in (cfg.dangerous_categories or [])
            }
            if is_dangerous and _risk_rank(risk) < _risk_rank("high"):
                risk = "high"
            meta = {
                "provider": "mcp",
                "server_id": td.server_id,
                "tool_name": td.tool_name,
                "transport": td.transport,
                "uri": td.uri,
                "signature": td.signature,
                "governance_state": "experimental",
                "category": td.category,
                # Default to untrusted output (prompt-injection safe wrapping can apply).
                "output_trust": "untrusted",
            }
            if isinstance(td.examples, list) and td.examples:
                meta["examples"] = td.examples

            # Tool learning v0: schema-based synthetic examples (disabled by default).
            if bool(cfg.enable_tool_learning) and not meta.get("examples") and isinstance(td.schema, dict) and td.schema:
                learner = ToolLearningModule(config=ToolLearningConfig(enabled=True, max_examples=int(cfg.tool_learning_max_examples)))
                meta = learner.maybe_augment_tool_meta(tool_name=tool_spec_name, meta=meta, input_schema=td.schema)

            spec = ToolSpec(
                name=tool_spec_name,
                description=td.description or f"MCP tool {td.server_id}/{td.tool_name}",
                kind=ToolKind.external,
                domain="core",
                risk_level=risk,
                lifecycle="candidate",
                input_schema=td.schema or {},
                output_schema={},
                meta=meta,
            )

            server = ServerDescriptor(
                server_id=td.server_id,
                transport=td.transport,
                uri=td.uri,
                auth_token=td.auth_token,
                metadata={},
            )

            def _handler(req, ctx=None, *, _server=server, _tool_name=td.tool_name, _invoker=invoker):
                arguments = dict(getattr(req, "payload", None) or {})
                # NOTE: tool manager already guards the call via SafetyKernel; this just executes.
                res = _invoker.invoke(server=_server, tool_name=_tool_name, arguments=arguments)
                if not res.success:
                    return {"status": "error", "error": res.error or "mcp_call_failed", "latency_ms": res.latency_ms}
                return {"status": "ok", "result": res.output, "latency_ms": res.latency_ms}

            try:
                tool_manager.register_tool(spec, _handler)
                registered.append(tool_spec_name)
            except Exception as e:  # noqa: BLE001
                errors.append({"tool": tool_spec_name, "error": str(e)})

        return ProviderReport(provider_id=self.provider_id, enabled=True, registered_tools=registered, errors=errors)
