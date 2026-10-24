from __future__ import annotations

import logging
import json
from typing import Any, Dict, List, Optional

from quentin.llm.client import call_llm
from quentin.memory.fabric import MemoryFabric
from quentin.memory.models import MemoryQuery, MemoryTier
from quentin.memory.kinds import KIND_GIST_MEMORY

logger = logging.getLogger(__name__)

async def compact_session_context(
    session_id: str,
    memory_fabric: MemoryFabric,
    model_router: Any,
    domain: str = "core"
) -> Dict[str, Any]:
    """
    P5: Ported from OpenClaw's direct session compaction logic.
    Summarizes recent session history into a 'gist' memory to free up context.
    """
    logger.info(f"Compaction: Starting for session {session_id}")
    
    # 1. Recall recent STS memories for this session
    # We look for memories tagged with this session
    query = MemoryQuery(
        text=f"session_id:{session_id}",
        tier=MemoryTier.STS,
        top_k=20
    )
    recent_mems = memory_fabric.recall(query)
    
    if len(recent_mems) < 3:
        return {"compacted": False, "reason": "too few memories to compact"}
        
    # 2. Build summarization prompt
    history_text = "\n".join([f"- {m.content}" for m in recent_mems])
    
    prompt = (
        f"Summarize the following recent agent activities and results for session {session_id}.\n"
        f"Identify the CURRENT STATE, successful accomplishments, and persistent roadblocks.\n"
        f"Keep it extremely concise (max 200 words).\n\n"
        f"HISTORY:\n{history_text}"
    )
    
    # 3. Call fast model for summarization
    cfg = model_router.route(mode="speed", task_type=domain)
    
    try:
        summary = call_llm(
            cfg,
            user_prompt=prompt,
            system_prompt="You are a system memory compressor. Summarize history into a 'gist'.",
            actor="compactor",
            domain=domain
        )
        
        if not summary or len(summary) < 10:
            return {"compacted": False, "reason": "LLM returned empty or too short summary"}
            
        # 4. Store the gist memory
        memory_fabric.remember_atomic(
            content=summary,
            source=f"compactor:{session_id}",
            tier=MemoryTier.STS,
            importance=0.7,
            tags=["gist", "compaction", f"session:{session_id}"],
            kind=KIND_GIST_MEMORY,
            domain=domain,
            metadata={"session_id": session_id, "original_count": len(recent_mems)}
        )
        
        # 5. Decay/Cleanup original records (mark as processed)
        memory_fabric.decay_records([m.id for m in recent_mems])
        
        logger.info(f"Compaction: Successfully compacted {len(recent_mems)} memories into a gist.")
        return {"compacted": True, "gist": summary, "count": len(recent_mems)}
        
    except Exception as e:
        logger.exception(f"Compaction: Failed for session {session_id}")
        return {"compacted": False, "error": str(e)}
