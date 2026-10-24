# OpenClaw Execution Tools Port Map (Taylor/Quentin)

Scope: `openclaw/openclaw/src/agents/tools/*` mapped to Quentin runtime/tooling.

Legend:
- `DONE`: tool exists and has a runnable benchmark or unit tests
- `PARTIAL`: core shape exists; missing production features (gateway integration, full action surface, policy gates)
- `MISSING`: no equivalent yet

## Core Tools

| OpenClaw file | Quentin equivalent | Tool name(s) | Status | Notes |
| --- | --- | --- | --- | --- |
| `web-fetch.ts` | `quentin/tools/execution_parity.py:web_fetch_tool` | `web.fetch` | DONE | SSRF guard, offline HTML, extractMode text/markdown, optional cache |
| `web-fetch-utils.ts` | `quentin/tools/execution_parity.py:_web_html_to_markdown/_web_markdown_to_text` | (internal) | PARTIAL | Regex-based; no DOM Readability dependency |
| `web-shared.ts` | `quentin/tools/execution_parity.py` (cache + helpers) | (internal) | PARTIAL | Minimal JSON cache, not full cache policy matrix |
| `web-tools.ts` | `quentin/tools/execution_parity.py:web_readability_tool` + `web_fetch_tool` + `web_search_tool` | `web.readability`, `web.fetch`, `web.search` | PARTIAL | Missing live-provider integration and richer ranking policy |
| `web-search.ts` | `quentin/tools/execution_parity.py:web_search_tool` | `web.search` | PARTIAL | Offline corpus/mock provider supported; live provider adapters still to be added |
| `image-tool.ts` | `quentin/tools/execution_parity.py:image_tool` | `image.tool` | DONE | OCR (vision stub + tesseract fallback) + features |
| `tts-tool.ts` | `quentin/tools/execution_parity.py:tts_tool` | `tts.tool` | DONE | Local TTS or text-write fallback |
| `canvas-tool.ts` | `quentin/tools/execution_parity.py:canvas_tool` | `canvas.tool` | PARTIAL | Local A2UI/component lifecycle; no gateway node.invoke backend |
| `nodes-tool.ts` | `quentin/tools/execution_parity.py:nodes_tool` | `nodes.tool` | PARTIAL | Strong local lease/leader logic; lacks full gateway node control surface |
| `agents-list-tool.ts` | `quentin/tools/execution_parity.py:agents_list_tool` | `agents.list` | PARTIAL | Lists local `data/subagent_status.json`, not OC allowlist-based config |
| `cron-tool.ts` | `quentin/tools/execution_parity.py:cron_tool` | `cron.tool` | DONE | Cron semantics + catch-up + run history (`action=runs`) |
| `session-status-tool.ts` | `quentin/tools/execution_parity.py:session_status_tool` | `session.status` | DONE | Includes listeners, queue, cron due, canvas ack pending, handoff graph |
| `sessions-announce-target.ts` | `quentin/tools/execution_parity.py:sessions_announce_target` | `sessions.announce_target` | DONE | Queue + consume/ack + handoff telemetry |
| `sessions-list-tool.ts` | `quentin/tools/execution_parity.py:sessions_list_tool` | `sessions.list` | DONE | Local aggregation: locks + tasks + system_events + subagents |
| `sessions-history-tool.ts` | `quentin/tools/execution_parity.py:sessions_history_tool` | `sessions.history` | DONE | Peeks system_events + recent task queue + announcements |
| `sessions-send-tool.ts` | `quentin/tools/execution_parity.py:sessions_send_tool` | `sessions.send` | DONE | `mode=system_event` or `mode=task_queue`, idempotency dedupe |
| `sessions-spawn-tool.ts` | `quentin/tools/execution_parity.py:sessions_spawn_tool` | `sessions.spawn` | DONE | Enqueues first task into isolated session |
| `memory-tool.ts` | `quentin/tools/execution_parity.py:memory_search_tool/memory_get_tool` | `memory.search`, `memory.get` | PARTIAL | File-based search/get for MEMORY.md/memory/docs; no semantic embeddings |
| `discord-actions*.ts` | `quentin/tools/execution_parity.py:discord_actions` + `channels_listener_tool(_async)` | `discord.actions`, `channels.listener` | PARTIAL | Send path + thread store + listener; missing OC's full guild/moderation/action surface |
| `slack-actions.ts` | `quentin/tools/execution_parity.py:slack_actions` + listener | `slack.actions`, `channels.listener` | PARTIAL | Webhook/adapter sends + thread store; lacks rich message actions |
| `telegram-actions.ts` | `quentin/tools/execution_parity.py:telegram_actions` + listener | `telegram.actions`, `channels.listener` | PARTIAL | Basic send + threading; lacks full action matrix |
| `whatsapp-actions.ts` | `quentin/tools/execution_parity.py:whatsapp_actions` | `whatsapp.actions` | PARTIAL | Minimal cloud API sender; no inbound monitor parity |
| `message-tool.ts` | `quentin/tools/execution_parity.py:message_tool` | `message.tool` | PARTIAL | Unified wrapper over platform tools + thread edit/delete/react + idempotency key dedupe; missing OC full moderation/workflow matrix |
| `browser-tool.ts` | `meta_agent/tools/browser/playwright_tool.py` (not a Quentin tool) | (none) | PARTIAL | Exists as meta-agent capability; not exposed as Quentin tool |
| `gateway-tool.ts` | `quentin/tools/execution_parity.py:gateway_tool` + `quentin/infra/channels/gateway_server.py` | `gateway.tool` | PARTIAL | Adds status/inbound/outbound wrapper + idempotency key dedupe; still lacks full OC gateway control surface |
| `agent-step.ts` | `quentin/tools/execution_parity.py:agent_step_tool` | `agent.step` | PARTIAL | Single-step execute/retry + error-kind classification; not yet tied to full OC step graph/state model |

## OpenClaw Tool Tests/Helpers

These are test/helper files in OC; Quentin equivalents are unit tests and benchmark scripts.

| OpenClaw file | Quentin equivalent | Status |
| --- | --- | --- |
| `web-tools.readability.test.ts` | `tests/unit/test_execution_parity_tools.py` + `scripts/execution_layer_benchmark.py` | DONE |
| `web-fetch.ssrf.test.ts` | `tests/unit/test_web_fetch_tool.py` | DONE |
| `cron-tool.test.ts` | `scripts/execution_layer_benchmark.py` + unit tests | DONE |
| `discord-actions.test.ts` | `tests/unit/test_execution_parity_tools.py` | PARTIAL |
| `slack-actions.test.ts` | `tests/unit/test_execution_parity_tools.py` | PARTIAL |
| `telegram-actions.test.ts` | `tests/unit/test_execution_parity_tools.py` | PARTIAL |
| `sessions-announce-target.test.ts` | `tests/unit/test_execution_parity_tools.py` | DONE |
