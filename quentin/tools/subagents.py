from __future__ import annotations

import uuid
import logging
import re
from typing import Any, Dict, List, Optional
from quentin.cognitive.loop import CognitiveTask, CognitiveLoop
from quentin.tools.schemas import ToolCallRequest, ToolCallResult
from quentin.multi_agent.subagent_registry import SubagentRegistry, SubagentRecord

logger = logging.getLogger(__name__)

class SubagentSpawnTool:
    """
    P5: Microscope Port of OpenClaw's sessions_spawn.
    """
    def __init__(self, cognitive_loop: CognitiveLoop):
        self.cognitive_loop = cognitive_loop
        self.registry = SubagentRegistry(cognitive_loop.repo_root)

    async def execute(self, params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
        # 1. Microscope Guard: No Nested Spawning
        md = {}
        if context:
            if hasattr(context, "metadata") and isinstance(context.metadata, dict):
                md = context.metadata
            elif isinstance(context, dict):
                md = context
        
        if md.get("is_subagent"):
            return {
                "status": "forbidden",
                "error": "sessions_spawn is not allowed from sub-agent sessions (Circular Prevention)."
            }

        # 2. Parameter Extraction (OpenClaw Parity)
        task_text = params.get("task")
        if not task_text:
            return {"status": "error", "error": "Missing 'task' description."}
        
        label = params.get("label", "subtask").strip() or "subtask"
        model_raw = params.get("model")
        think_level = params.get("thinking", "off")
        cleanup = params.get("cleanup", "keep")
        timeout = float(params.get("runTimeoutSeconds") or params.get("timeoutSeconds") or 300)

        # 3. Model Ref Parsing (provider/model)
        provider, model_id = self._parse_model_ref(model_raw)
        
        parent_session_id = str(md.get("session_id") or "main")
        child_session_id = f"subagent:{uuid.uuid4().hex[:12]}"
        
        # 4. Registry Logging (Before execution)
        record = SubagentRecord(
            run_id=uuid.uuid4().hex,
            child_session_id=child_session_id,
            parent_session_id=parent_session_id,
            task=task_text,
            label=label,
            status="pending",
            model=model_id or "default",
            cleanup=cleanup
        )
        self.registry.register(record)

        # 5. Build Recursive Task
        sub_task = CognitiveTask(
            input_text=task_text,
            task_id=child_session_id,
            metadata={
                "spawned_by": parent_session_id,
                "label": label,
                "is_subagent": True,
                "model_override": model_id,
                "provider_override": provider,
                "think_level": think_level,
                "timeout": timeout
            }
        )
        
        print(f"🚀 [Spawn] Launching sub-agent process: {label} (Model: {model_id or 'default'})")
        
        try:
            # 6. Structured Join (Await Result)
            # We wrap this in a timeout guard to match OpenClaw
            import asyncio
            result = await asyncio.wait_for(
                self.cognitive_loop.run_task_async(sub_task),
                timeout=timeout
            )
            
            # P5: Microscope Port - Result Sanitization & Tagging
            raw_output = str(result.final_output or "").strip()
            
            # Update Registry with result
            self.registry.update_status(
                child_session_id=child_session_id, 
                status="completed" if result.done else "partial",
                result_summary=raw_output[:200]
            )

            # Smart Truncation: If output is massive, keep head/tail and notify
            MAX_RETURN_CHARS = 2500
            if len(raw_output) > MAX_RETURN_CHARS:
                processed_output = (
                    raw_output[:1200] + 
                    f"\n\n... [TRUNCATED {len(raw_output) - MAX_RETURN_CHARS} CHARS FOR CONTEXT SAFETY] ...\n\n" + 
                    raw_output[-1200:]
                )
            else:
                processed_output = raw_output

            # Wrapped in XML Protocol for parent perception
            tagged_result = f"""
<subagent_result id="{child_session_id}" status="{"ok" if result.done else "partial"}">
{processed_output}
</subagent_result>
"""
            return {
                "status": "ok",
                "child_session_id": child_session_id,
                "result": tagged_result,
                "done": result.done,
                "metrics": result.to_dict().get("metrics")
            }
        except asyncio.TimeoutError:
            logger.error(f"SubagentSpawn: Subagent {child_session_id} timed out.")
            return {"status": "error", "error": f"Sub-agent timed out after {timeout}s", "child_session_id": child_session_id}
        except Exception as e:
            logger.error(f"SubagentSpawn: Subagent {child_session_id} failed: {e}")
            return {"status": "error", "error": str(e), "child_session_id": child_session_id}

    def _parse_model_ref(self, ref: Any) -> tuple[Optional[str], Optional[str]]:
        if not ref or not isinstance(ref, str):
            return None, None
        
        parts = ref.strip().split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return None, parts[0]

def create_subagent_pack(cognitive_loop: CognitiveLoop) -> List[Dict[str, Any]]:
    spawn_tool = SubagentSpawnTool(cognitive_loop)
    return [
        {
            "name": "sessions_spawn",
            "description": "Spawn a background sub-agent to handle a specific sub-task in isolation.",
            "handler": spawn_tool.execute,
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The specific mission for the sub-agent."},
                    "label": {"type": "string", "description": "A short label for this sub-task."},
                    "model": {"type": "string", "description": "Model override in 'provider/model' format (e.g. 'openai/gpt-4')."},
                    "thinking": {"type": "string", "enum": ["off", "low", "medium", "high"], "description": "Thinking level for sub-agent."},
                    "runTimeoutSeconds": {"type": "number", "description": "Maximum execution time."},
                    "cleanup": {"type": "string", "enum": ["delete", "keep"], "default": "keep"}
                },
                "required": ["task"]
            }
        }
    ]
