from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from quentin.cognitive.loop import CognitiveLoop, CognitiveTask
from quentin.bootstrap.container import Container
from quentin.runtime.system_events import SystemEventQueue
from quentin.runtime.output_projection import (
    visible_output_from_brain_events,
    has_message_final_brain_event,
)

logger = logging.getLogger(__name__)

# --- Models for StandardAgentAPI ---

class TaskRequest(BaseModel):
    input_text: str
    session_id: Optional[str] = None
    domain: str = "core"
    environment: str = "sandbox"
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TaskResponse(BaseModel):
    task_id: str
    goal_id: str
    status: str
    final_output: Optional[str] = None

class AgentStatus(BaseModel):
    agent_id: str
    status: str
    capabilities: List[str]
    active_tasks: int

# --- API Implementation ---

class StandardAgentAPI:
    """
    StandardAgentAPI (Gap 6.2):
    Exposes Taylor's CognitiveLoop as a standard REST API that 
    OpenClaw or other external 'bodies' can consume.
    """
    def __init__(self, cognitive_loop: Optional[CognitiveLoop] = None):
        self.app = FastAPI(title="Taylor StandardAgentAPI")
        self.loop = cognitive_loop or Container().cognitive_loop
        self.event_queue = SystemEventQueue(repo_root=".")
        self._setup_routes()
        self._active_tasks: Dict[str, str] = {} # task_id -> status

    def _setup_routes(self):
        @self.app.get("/status", response_model=AgentStatus)
        async def get_status():
            return AgentStatus(
                agent_id="taylor-quentin-01",
                status="online",
                capabilities=["self-programming", "reasoning", "multi-modal-perception"],
                active_tasks=len(self._active_tasks)
            )

        @self.app.post("/tasks", response_model=TaskResponse)
        async def create_task(request: TaskRequest, background_tasks: BackgroundTasks):
            task_id = str(uuid.uuid4())
            metadata = {**(request.metadata or {}), "session_id": request.session_id or task_id}
            
            cognitive_task = CognitiveTask(
                input_text=request.input_text,
                task_id=task_id,
                domain=request.domain,
                environment=request.environment,
                metadata=metadata
            )

            self._active_tasks[task_id] = "running"
            
            # For simplicity in this first version, we run it synchronously in a thread
            # In a production setup, this would be a real background task with status polling
            try:
                # We use the existing loop.run_task which is sync-but-calls-async
                result = await asyncio.to_thread(self.loop.run_task, cognitive_task)
                self._active_tasks.pop(task_id, None)
                final_output = str(getattr(result, "final_output", "") or "")
                try:
                    events = self.event_queue.list_brain_events(
                        session_id=str(metadata.get("session_id") or task_id),
                        limit=400,
                    )
                    projected = visible_output_from_brain_events(events, turn_id=task_id)
                    has_final = has_message_final_brain_event(events, turn_id=task_id)
                    if projected or has_final:
                        final_output = projected
                except Exception:
                    pass
                
                return TaskResponse(
                    task_id=task_id,
                    goal_id=result.goal_id,
                    status="completed" if result.done else "failed",
                    final_output=final_output
                )
            except Exception as e:
                self._active_tasks.pop(task_id, None)
                logger.exception(f"API Task failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/tasks/{task_id}", response_model=TaskResponse)
        async def get_task(task_id: str):
            if task_id in self._active_tasks:
                return TaskResponse(task_id=task_id, goal_id="pending", status=self._active_tasks[task_id])
            raise HTTPException(status_code=404, detail="Task not found or completed")

# Singleton for the app
agent_api = StandardAgentAPI()
app = agent_api.app
