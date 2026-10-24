from __future__ import annotations

import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

class AudioBridge:
    """
    Handles real-time audio/voice communication.
    Bridges Whisper (STT) and Sherpa-ONNX/OpenAI (TTS).
    Includes VAD (Voice Activity Detection) for atomic parity.
    """
    def __init__(self):
        self.stt_engine = "whisper"
        self.tts_engine = "openai"
        self._silence_threshold = 0.01 # Energy threshold
        self._silence_limit_sec = 1.5

    async def detect_silence(self, stream: AsyncIterator[bytes]) -> bool:
        """
        Atomic-level VAD logic. 
        Detects when the user stops speaking.
        """
        import numpy as np
        silence_start = None
        
        async for chunk in stream:
            # Calculate energy (simplified Silero-VAD approach)
            audio_data = np.frombuffer(chunk, dtype=np.int16)
            energy = np.mean(np.abs(audio_data)) / 32768.0
            
            if energy < self._silence_threshold:
                if silence_start is None:
                    silence_start = time.time()
                elif (time.time() - silence_start) > self._silence_limit_sec:
                    logger.info("VAD: End of speech detected.")
                    return True
            else:
                silence_start = None
        return False

# Global instance
audio_bridge = AudioBridge()
