# Input Preprocessor + Command Plugin Guide

## Purpose

Before LLM execution, Quentin now runs a deterministic preprocessing pipeline:

1. Routing signal extraction (`@mention`)
2. Command short-circuit (`/status`, `/reset`, or plugin commands)
3. Inline deterministic action (`/tool <tool_name> <json_args>`, allowlisted)
4. Directive extraction (`/thinking high`)
5. Send cleaned intent text to reflex/LLM path

This reduces protocol fragility and keeps control/config logic in code.

Directive policy:
- `QUENTIN_INPUT_DIRECTIVE_ALLOWLIST` controls which directives are applied (`*` means all).
- `QUENTIN_INPUT_DIRECTIVE_PERSIST=0` applies directive for current parse only (does not persist into task metadata).

## Pipeline Location

- Preprocessor: `quentin/cognitive/input_preprocessor.py`
- Entry integration: `quentin/cognitive/loop_entrypoints.py`

## Environment Variables

### Core switches

- `QUENTIN_INPUT_PREPROCESS_ENABLED=1`
- `QUENTIN_INPUT_COMMANDS_ENABLED=1`
- `QUENTIN_INPUT_DIRECTIVES_ENABLED=1`
- `QUENTIN_INPUT_MENTIONS_ENABLED=1`
- `QUENTIN_INPUT_COMMAND_PREFIX=/`
- `QUENTIN_INPUT_DIRECTIVE_ALLOWLIST=thinking`
- `QUENTIN_INPUT_DIRECTIVE_PERSIST=1`
- `QUENTIN_INPUT_INLINE_ACTIONS_ENABLED=1`
- `QUENTIN_INPUT_INLINE_ACTION_TOOL_ALLOWLIST=fs.exists,fs.read_file,shell.run_command`
- `QUENTIN_INPUT_INLINE_ACTION_SHELL_ALLOWLIST=pwd,ls,id,which`

### Mention routing

- `QUENTIN_INPUT_ROUTE_BY_MENTION=0`
- `QUENTIN_INPUT_MENTION_ROUTE_MAP=research:research,coding:maintenance`

When `QUENTIN_INPUT_ROUTE_BY_MENTION=1`, first matching mention can map domain.

### Command registry control

- `QUENTIN_INPUT_COMMAND_ALLOWLIST=*`
- `QUENTIN_INPUT_COMMAND_HANDLERS=`

`QUENTIN_INPUT_COMMAND_ALLOWLIST` accepts:
- `*` for all registered commands
- comma list, e.g. `status,reset,ping`

`QUENTIN_INPUT_COMMAND_HANDLERS` accepts comma-separated plugin specs:
- `module:function,module2:function2`

Each function is called with `registry` and should register commands.

### Inline action policy

- Syntax: `/tool <tool_name> <json_args>`
- Only allowlisted tools can run deterministically.
- For `shell.run_command`, command head must match `QUENTIN_INPUT_INLINE_ACTION_SHELL_ALLOWLIST`.
- If blocked or execution fails, pipeline falls back to planner path (no hard failure).

## Plugin Contract

Register function signature:

```python
def register_commands(registry):
    ...
```

Command handler signature:

```python
async def handler(ctx):
    return {
        "status": "ok",
        "final_output": "...",
        "actions_summary": "command:/your_command",
    }
```

`ctx` is `CommandExecutionContext` with:
- `ctx.loop`
- `ctx.task`
- `ctx.parsed`
- `ctx.session_id`

## Minimal Plugin Example

```python
# my_project/quentin_cmd_plugins.py
async def _ping(ctx):
    return {
        "status": "ok",
        "final_output": f"pong:{ctx.session_id}",
        "actions_summary": "command:/ping",
    }

def register_commands(registry):
    registry.register("ping", _ping)
```

`.env`:

```bash
QUENTIN_INPUT_COMMAND_HANDLERS=my_project.quentin_cmd_plugins:register_commands
QUENTIN_INPUT_COMMAND_ALLOWLIST=status,reset,ping
```

Input:

```text
/ping
```

Result: deterministic command execution, no LLM roundtrip.

## Failure Behavior

- Invalid plugin spec is skipped with warning.
- Plugin import/register failure is isolated; other plugins still load.
- Command not in allowlist is treated as normal user text (continues pipeline).
