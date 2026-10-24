import subprocess
import re
import logging
import os
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class GeminiCLIWrapper:
    """
    Advanced wrapper for Gemini CLI with TTY-bypass and context injection.
    """
    def __init__(self, binary_path: str = "gemini"):
        self.binary_path = binary_path

    def create_prompt(self, task: str, code_context: str = "") -> str:
        template = (
            "You are an expert developer. Environment: NON-INTERACTIVE.\n"
            "CONTEXT:\n{context}\n\n"
            "TASK: {task}\n\n"
            "Return implementation in ```python ... ```"
        )
        return template.format(context=code_context, task=task)

    def run_command(self, prompt: str, timeout: int = 120) -> Dict[str, Any]:
        # Force non-interactive mode via env vars common to many CLIs
        env = os.environ.copy()
        env["TERM"] = "dumb"
        env["PYTHONUNBUFFERED"] = "1"
        
        cmd = [self.binary_path, "ask", prompt]
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=timeout,
                env=env
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def parse_code_blocks(self, output: str) -> List[str]:
        pattern = r"```(?:[a-zA-Z0-9]+)?\n?(.*?)```"
        blocks = re.findall(pattern, output, re.DOTALL)
        return [b.strip() for b in blocks]