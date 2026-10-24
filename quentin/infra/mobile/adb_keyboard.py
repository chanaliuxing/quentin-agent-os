from __future__ import annotations

import logging
import base64
from typing import Optional
from .adb_client import adb_client

logger = logging.getLogger(__name__)

class ADBKeyboard:
    """
    High-precision text injection for Android.
    Matches OpenClaw's implementation for handling spaces and Unicode.
    """
    
    @staticmethod
    def type_safely(text: str):
        """
        Injects text using a broadcast-based method (via ADB keyboard).
        Standard 'input text' breaks on spaces and emojis.
        """
        # 1. Base64 encode the text to preserve spaces and Unicode
        encoded_text = base64.b64encode(text.encode('utf-8')).decode('utf-8')
        
        # 2. Use ADB broadcast to the ADBKeyBoard (assumes ADBKeyboard.apk is installed)
        # Fallback to escaped 'input text' if IME not available
        logger.info(f"ADB: Injecting text via broadcast: {text[:20]}...")
        
        # Command syntax from OpenClaw's adb helper
        cmd = [
            "shell", "am", "broadcast", "-a", "ADB_INPUT_TEXT", 
            "--es", "msg", encoded_text
        ]
        res = adb_client.run_cmd(cmd)
        
        if "result=0" not in res:
            # Fallback to escaped shell command
            logger.warning("ADB: ADBKeyboard not found, falling back to escaped input.")
            escaped = text.replace(" ", "%s").replace("'", "'")
            adb_client.run_cmd(["shell", "input", "text", escaped])

# Global instance
keyboard = ADBKeyboard()
