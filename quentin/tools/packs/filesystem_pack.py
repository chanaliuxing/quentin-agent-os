from __future__ import annotations
from pathlib import Path
from typing import List, Tuple, Any, Dict
from quentin.tools.packs.base import ToolPack
from quentin.tools.schemas import ToolSpec, ToolKind

class FileSystemToolPack(ToolPack):
    @property
    def domain(self) -> str:
        return "fs"

    def get_tools(self) -> List[Tuple[ToolSpec, Any]]:
        from quentin.tools.filesystem import fs_read_file, fs_write_file, fs_get_write_policy, fs_search_replace, fs_mkdir
        
        # Define Specs
        read_spec = ToolSpec(
            name="fs.read_file",
            description="Read content from a file.",
            domain="fs"
        )
        write_spec = ToolSpec(
            name="fs.write_file",
            description="Write content to a file.",
            domain="fs"
        )
        write_policy_spec = ToolSpec(
            name="fs.get_write_policy",
            description="Get current writable roots enforced by PathGuard.",
            domain="fs",
        )
        mkdir_spec = ToolSpec(
            name="fs.mkdir",
            description="Create a directory (idempotent).",
            domain="fs"
        )
        
        # Add new frequently hallucinated tools
        def fs_exists_impl(params, ctx=None):
            p = Path(params.get("path", ".")).resolve()
            return {"exists": p.exists(), "is_dir": p.is_dir()}
            
        exists_spec = ToolSpec(
            name="fs.exists",
            description="Check if a file or directory exists.",
            domain="fs"
        )

        return [
            (read_spec, fs_read_file),
            (write_spec, fs_write_file),
            (write_policy_spec, fs_get_write_policy),
            (exists_spec, fs_exists_impl),
            (mkdir_spec, fs_mkdir)
        ]
