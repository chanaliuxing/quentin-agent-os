from __future__ import annotations
import os
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class WorkspaceFactory:
    """
    P5: Ported from OpenClaw's ephemeral workspace isolation.
    Creates a 'Symlink Farm' to simulate Copy-on-Write isolation for sub-agents.
    """
    
    @staticmethod
    def create_ephemeral_workspace(
        source_root: str | Path, 
        session_id: str,
        base_storage: str | Path = ".quentin/workspaces"
    ) -> Path:
        """
        Builds a shadow workspace where writes don't affect the source immediately.
        """
        src = Path(source_root).resolve()
        dest = Path(base_storage).resolve() / session_id
        
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        
        # 1. Symlink Farm (OpenClaw Parity)
        # We walk source and recreate directory structure, then symlink files.
        # This is faster than copying GBs of node_modules.
        ignore = {".git", ".quentin", "__pycache__", "venv"}
        
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in ignore]
            
            rel_path = Path(root).relative_to(src)
            target_dir = dest / rel_path
            target_dir.mkdir(parents=True, exist_ok=True)
            
            for f in files:
                source_file = Path(root) / f
                target_file = target_dir / f
                try:
                    # Absolute path for symlink is safer
                    os.symlink(source_file, target_file)
                except Exception as e:
                    logger.warning(f"WorkspaceFactory: Failed to link {f}: {e}")
                    
        logger.info(f"WorkspaceFactory: Isolated workspace created at {dest}")
        return dest

    @staticmethod
    def merge_back(
        ephemeral_root: str | Path, 
        target_root: str | Path
    ) -> List[str]:
        """
        Commits changes from the ephemeral workspace back to the main repo.
        """
        src = Path(ephemeral_root).resolve()
        dest = Path(target_root).resolve()
        changed = []
        
        for root, dirs, files in os.walk(src):
            rel_path = Path(root).relative_to(src)
            target_dir = dest / rel_path
            
            for f in files:
                ephemeral_file = Path(root) / f
                # 2. Detect Modified Files (OpenClaw Parity)
                # If it's NOT a symlink, it means it was written to (Copy-on-Write)
                if not ephemeral_file.is_symlink():
                    target_file = target_dir / f
                    # Atomic Copy
                    shutil.copy2(ephemeral_file, target_file)
                    changed.append(str(target_file.relative_to(dest)))
                    
        logger.info(f"WorkspaceFactory: Merged {len(changed)} files back to main.")
        return changed
