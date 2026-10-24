from __future__ import annotations

import logging
import asyncio
from typing import Any, Dict, List, Optional
from .base import ChannelAdapter, InboundMessage
from quentin.cognitive.loop import CognitiveLoop, CognitiveTask
from quentin.runtime.system_events import SystemEventQueue
from quentin.runtime.output_projection import (
    visible_output_from_brain_events,
    has_message_final_brain_event,
)

from .pairing import PairingManager

logger = logging.getLogger(__name__)

class ChannelBridge:
    """
    Bridges communication channels with the Cognitive Loop.
    Converts mobile messages into CognitiveTasks and routes results back.
    """
    def __init__(self, loop: CognitiveLoop, adapters: List[ChannelAdapter], pairing_manager: Optional[PairingManager] = None):
        self.loop = loop
        self.adapters = adapters
        self.pairing_manager = pairing_manager or PairingManager()
        self.system_event_queue = SystemEventQueue(repo_root=".")
        
        # Register callback for all adapters
        for adapter in self.adapters:
            adapter.set_on_message(self.handle_message)

    async def handle_message(self, message: InboundMessage):
        chat_id = message.metadata.get("chat_id")
        
        # Find the correct adapter to reply with
        adapter = next((a for a in self.adapters if a.name == message.channel_id), None)
        if not adapter:
            logger.error(f"Bridge: No adapter found for channel {message.channel_id}")
            return

        # 1. Security Check (Pairing)
        if not self.pairing_manager.is_trusted(message.sender_id):
            if message.text.startswith("/pair "):
                code = message.text.split(" ")[1].strip()
                approved_id = self.pairing_manager.approve_code(code)
                if approved_id == message.sender_id:
                    await adapter.send_text(chat_id, "✅ 配对成功！你现在可以控制大脑了。")
                else:
                    await adapter.send_text(chat_id, "❌ 配对码无效或已过期。")
                return
            
            # Not trusted, generate a new pairing request
            new_code = self.pairing_manager.generate_pairing_code(message.sender_id)
            logger.warning(f"Bridge: Unauthorized sender {message.sender_id}. Generated code: {new_code}")
            
            msg = (
                "⚠️ 未经授权的访问。\n"
                f"你的 ID: {message.sender_id}\n"
                f"配对码: {new_code}\n\n"
                "请在大脑控制台输入此代码以授权。"
            )
            await adapter.send_text(chat_id, msg)
            return

        logger.info(f"Bridge: Received message from {message.sender_id}: {message.text[:50]}...")
        
        # 1. Create a CognitiveTask
        task = CognitiveTask(
            input_text=message.text,
            domain="mobile",
            metadata={
                "session_id": str(chat_id or message.sender_id or "mobile"),
                "channel": message.channel_id,
                "sender_id": message.sender_id,
                "chat_id": message.metadata.get("chat_id")
            }
        )

        # 2. Run the task through the brain
        # We use to_thread because CognitiveLoop.run_task might be blocking/sync in some implementations
        try:
            # Send an immediate 'ack' to the phone
            await adapter.send_text(
                message.metadata.get("chat_id"), 
                "🧠 大脑正在思考中..."
            )

            result = await asyncio.to_thread(self.loop.run_task, task)

            # 3. Send results back to phone via event protocol (message.final).
            sid = str((task.metadata or {}).get("session_id") or "mobile")
            brain_events = self.system_event_queue.list_brain_events(session_id=sid, limit=400)
            final_text = visible_output_from_brain_events(
                brain_events,
                turn_id=str(getattr(task, "task_id", "") or ""),
            )
            has_final = has_message_final_brain_event(
                brain_events,
                turn_id=str(getattr(task, "task_id", "") or ""),
            )
            if not final_text and not has_final:
                final_text = str(getattr(result, "final_output", "") or "")

            response_text = f"✅ 任务完成\n\n{final_text}"
            if len(response_text) > 4000:
                response_text = response_text[:3990] + "..."
                
            await adapter.send_text(
                message.metadata.get("chat_id"), 
                response_text
            )
        except Exception as e:
            logger.exception("Bridge: Error processing mobile task")
            await adapter.send_text(
                message.metadata.get("chat_id"), 
                f"❌ 处理出错: {str(e)}"
            )

    async def start(self):
        for adapter in self.adapters:
            await adapter.start()

    async def stop(self):
        for adapter in self.adapters:
            await adapter.stop()
