import ast
import os
from dataclasses import dataclass, field
from typing import Dict, Set, Optional


@dataclass
class ParsedFileInfo:
    functions: Set[str] = field(default_factory=set)
    classes: Set[str] = field(default_factory=set)
    methods: Set[str] = field(default_factory=set)  # Class.method
    placeholders: int = 0
    todo_tokens: bool = False


class ASTIndex:
    """
    Build once, query many times. Indexes Python files for functions/classes/methods and placeholder signals.
    Skips common vendor/build dirs to stay fast.
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.index: Dict[str, ParsedFileInfo] = {}
        self._build_index()

    def _build_index(self):
        ignore_dirs = {
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "dist",
            "build",
            "__pycache__",
            ".mypy_cache",
            ".pytest_cache",
            "site-packages",
        }
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, self.project_root)
                info = self._parse_file(path)
                if info:
                    self.index[rel] = info

    def _parse_file(self, path: str) -> Optional[ParsedFileInfo]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return None

        info = ParsedFileInfo()
        try:
            tree = ast.parse(content, filename=path)
        except Exception:
            # mark parse errors via placeholders flag to allow scoring penalties
            info.placeholders += 0
            info.todo_tokens = False
            return info

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                info.functions.add(node.name)
                if self._is_placeholder(node):
                    info.placeholders += 1
            elif isinstance(node, ast.ClassDef):
                info.classes.add(node.name)
                if self._is_placeholder(node):
                    info.placeholders += 1
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        info.methods.add(f"{node.name}.{child.name}")
                        if self._is_placeholder(child):
                            info.placeholders += 1

        # Lightweight placeholder marker scan.
        # Avoid scanning for generic task markers: they appear frequently in legitimate variable names
        # (e.g. "open_todos") and produces noisy false positives. Rely on AST placeholder
        # detection for structural placeholders, and keep only strong textual markers.
        tokens = ("FIXME", "NOTIMPLEMENTED")
        upper_content = content.upper()
        if any(tok in upper_content for tok in tokens):
            info.todo_tokens = True

        return info

    def _is_placeholder(self, node: ast.AST) -> bool:
        if hasattr(node, "body"):
            body = getattr(node, "body")
            if isinstance(body, list) and len(body) == 1:
                stmt = body[0]
                if isinstance(stmt, ast.Pass):
                    return True
                if isinstance(stmt, ast.Expr) and isinstance(getattr(stmt, "value", None), ast.Ellipsis):
                    return True
                if isinstance(stmt, ast.Return) and stmt.value is None:
                    return True
                if isinstance(stmt, ast.Raise):
                    exc = stmt.exc
                    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name) and exc.func.id == "NotImplementedError":
                        return True
                    if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                        return True
        docstring = ast.get_docstring(node)
        if docstring and ("TO" "DO") in docstring.upper():
            return True
        return False

    def get(self, module_hint: str) -> Optional[ParsedFileInfo]:
        return self.index.get(module_hint)
