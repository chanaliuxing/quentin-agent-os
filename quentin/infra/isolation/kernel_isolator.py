from __future__ import annotations
import platform
import logging
import shlex
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class KernelIsolator:
    """
    P5: Ported from OpenClaw's kernel-level namespace gating.
    Wraps shell commands with OS-native isolation primitives (unshare/sandbox-exec).
    """
    
    @staticmethod
    def wrap_command(command: str, restricted: bool = False) -> str:
        """
        Injects kernel-level isolation flags into the command string.
        """
        system = platform.system().lower()
        
        # 1. Linux: Namespace Isolation (unshare)
        if system == "linux":
            # --map-root-user: fake root for installation tasks
            # --net: isolate network if restricted
            # --pid --fork: isolate process tree
            ns_flags = "--map-root-user --pid --fork --mount-proc"
            if restricted:
                ns_flags += " --net" # Hard network cutoff
                
            logger.info(f"KernelIsolator: Applying Linux Namespace Isolation")
            return f"unshare {ns_flags} /bin/bash -c {shlex.quote(command)}"
            
        # 2. Darwin (macOS): Sandbox-exec (App Sandbox)
        elif system == "darwin":
            # macOS uses sandbox profiles. We use a 'no-network' profile if restricted.
            if restricted:
                logger.info(f"KernelIsolator: Applying Darwin Sandbox (No-Network)")
                return f"sandbox-exec -p '(version 1)(deny network*)(allow default)' {command}"
            return command
            
        return command
