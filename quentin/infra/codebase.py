from pathlib import Path
from typing import Optional
from quentin.infra.env import get_project_root


class CodebaseAccessor:
    """
    提供统一的源码访问接口（只读）：
    - 按相对路径读取模块源码
    - 限制在项目根目录之内
    """

    def __init__(self, root: Optional[Path] = None):
        self.root = root or get_project_root()

    def resolve_module_path(self, relative_path: str) -> Path:
        p = (self.root / relative_path).resolve()
        if self.root not in p.parents and self.root != p:
            # Check if p is inside or equal to self.root
            if not p.is_relative_to(self.root):
                raise PermissionError(f"Path {p} escapes project root {self.root}")
        return p


    def read_source(self, relative_path: str) -> str:
        path = self.resolve_module_path(relative_path)
        if not path.exists():
            raise FileNotFoundError(f"Module not found: {relative_path}")
        return path.read_text(encoding="utf-8")
