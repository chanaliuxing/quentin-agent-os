# MCP Setup & Config

- **Registry index**: provide MCP servers via JSON. Defaults searched:
  - `MCP_REGISTRY_INDEX_PATHS` (os.pathsep-separated)
  - `config/mcp_registry.json`
  - `config/mcp/registry.json`
  - `data/mcp_registry.json`
- **Sample**: see `config/mcp_registry.sample.json`.
- **Env**:
  - `MCP_REGISTRY_INDEX_PATHS=/path/to/registry.json`
  - `TOOL_USAGE_TRUNCATE_LEN=2000` (truncate inputs/outputs/errors when persisting TOOL_KNOWLEDGE usage examples)
- **Invoker**:
  - Requires `pip install mcp` and stdio servers reachable at the `uri` in registry.
  - Supports `transport=stdio` today; extend to websocket/SSE as needed.
- **Lifecycle**:
  - `CouncilBackedToolGate` uses CouncilRuntime for `experimental -> trusted` upgrades.
  - `ToolLifecycleManager` wraps registry updates; persists council_score placeholder.
- **Memory sync**:
  - Set `sync_tool_knowledge=True` on TaskExecutor to write TOOL_KNOWLEDGE (metadata + usage examples) to Memory Fabric after calls.
