from __future__ import annotations
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ToolDisplay:
    """
    P5: Ported from OpenClaw's tool-title-formatter.
    Converts raw tool names and args into human-readable task descriptions.
    """
    
    @staticmethod
    def format_tool_title(name: str, args: Dict[str, Any]) -> str:
        """
        Produces an emoji-enriched, semantic title for a tool call.
        """
        # 1. Base Mapping
        mapping = {
            "fs.read_file": "📖 Reading",
            "fs.write_file": "📝 Writing",
            "fs.search_replace": "✂️ Patching",
            "shell.run_command": "🐚 Executing",
            "browser.navigate": "🌐 Navigating",
            "browser.observe": "👁️ Observing",
            "memory.search": "🧠 Recalling",
        }
        
        prefix = mapping.get(name, "🛠️ Running")
        
        # 2. Argument Extraction
        target = ""
        for key in ["path", "file_path", "url", "command"]:
            if key in args:
                val = str(args[key])
                # Truncate long commands
                if len(val) > 40: val = val[:37] + "..."
                target = f" {val}"
                break
                
        return f"{prefix}{target} ({name})"

def resolve_tool_display(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    P5: Ported from OpenClaw's tool-resolver.
    Resolves raw tool metadata into a display-friendly structure.
    """
    title = ToolDisplay.format_tool_title(name, args)
    return {
        "name": name,
        "args": args,
        "title": title,
        "icon": title.split(" ")[0] if " " in title else "🛠️"
    }

def format_tool_summary(display: Dict[str, Any]) -> str:
    """
    Formats a tool display object into a final summary string.
    """
    return str(display.get("title") or "Unknown action")

