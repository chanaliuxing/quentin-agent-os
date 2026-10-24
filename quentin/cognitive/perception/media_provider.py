from __future__ import annotations

import os
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional
from quentin.cognitive.perception.base import PerceptionProvider
from quentin.llm.client import call_llm

class MediaPerceptionProvider(PerceptionProvider):
    """
    P5: Ported from OpenClaw's media understanding.
    Handles images, audio, and video understanding by converting them to text descriptions.
    """
    def __init__(self, repo_root: Path, model_router: Any):
        self.repo_root = repo_root
        self.model_router = model_router

    def get_perception_data(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes media attachments provided in the context.
        """
        attachments = ctx.get("attachments", [])
        if not attachments:
            return {}

        outputs = []
        for attachment in attachments:
            kind = attachment.get("kind")
            if kind == "image":
                desc = self._describe_image(attachment, ctx)
                if desc:
                    outputs.append({"kind": "image.description", "text": desc, "source": attachment.get("path")})
            elif kind == "audio":
                transcript = self._transcribe_audio(attachment, ctx)
                if transcript:
                    outputs.append({"kind": "audio.transcription", "text": transcript, "source": attachment.get("path")})
        
        return {"media_understanding": outputs} if outputs else {}

    def _describe_image(self, attachment: Dict[str, Any], ctx: Dict[str, Any]) -> Optional[str]:
        path = attachment.get("path")
        if not path:
            return None
            
        full_path = self.repo_root / path
        if not full_path.exists():
            return None

        try:
            with open(full_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            
            # Call vision-capable model
            cfg = self.model_router.route(mode="executor", task_type="vision")
            prompt = "Describe this image in detail for an AI agent to understand the context."
            
            res = call_llm(
                cfg,
                user_prompt=prompt,
                system_prompt="You are a vision perception module.",
                images=[img_data],
                actor="perception_vision"
            )
            return res
        except Exception as e:
            return f"Error understanding image: {e}"

    def _transcribe_audio(self, attachment: Dict[str, Any], ctx: Dict[str, Any]) -> Optional[str]:
        # Placeholder for audio transcription logic
        # In a real implementation, this would call Whisper or a similar service
        return f"[Audio file attached: {attachment.get('path')}]"
