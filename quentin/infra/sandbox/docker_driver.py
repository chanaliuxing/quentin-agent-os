from __future__ import annotations
import subprocess
import logging
import uuid
import time
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class DockerSandboxDriver:
    """
    Tier 0 Isolation Engine: Executes commands inside a Docker container.
    """
    def __init__(self, image: str = "python:3.11-slim", workspace_mount: str = "/workspace"):
        self.image = image
        self.container_name = f"taylor_sandbox_{uuid.uuid4().hex[:8]}"
        self.workspace_mount = workspace_mount
        self._is_active = False

    def is_available(self) -> bool:
        """Check if docker daemon is reachable."""
        try:
            subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def start(self, host_cwd: str) -> None:
        """Start the persistent sandbox container."""
        if not self.is_available():
            raise RuntimeError("Docker is not available.")
        
        logger.info(f"Starting sandbox container: {self.container_name}")
        
        # Start a sleeper container
        cmd = [
            "docker", "run", "-d", "--rm",
            "--name", self.container_name,
            "-v", f"{host_cwd}:{self.workspace_mount}",
            "-w", self.workspace_mount,
            self.image,
            "sleep", "infinity"
        ]
        
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        self._is_active = True
        
        # Install basic tools if needed (optional)
        # self.exec_run("apt-get update && apt-get install -y git curl")

    def stop(self) -> None:
        """Kill the sandbox."""
        if self._is_active:
            subprocess.run(["docker", "kill", self.container_name], stderr=subprocess.DEVNULL)
            self._is_active = False

    def exec_run(self, command: str, timeout: int = 60) -> Tuple[int, str, str]:
        """
        Execute command inside the container.
        Returns: (exit_code, stdout, stderr)
        """
        if not self._is_active:
            raise RuntimeError("Sandbox not started.")

        # Use docker exec
        exec_cmd = [
            "docker", "exec",
            self.container_name,
            "sh", "-c", command
        ]
        
        try:
            res = subprocess.run(
                exec_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return res.returncode, res.stdout, res.stderr
        except subprocess.TimeoutExpired:
            return 124, "", f"Timeout after {timeout}s"
