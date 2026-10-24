# meta_agent/self_programming/infra/context_extractor.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
import ast
from pathlib import Path


@dataclass
class ContextChunk:
    file_path: str
    content: str


def summarize_file_signatures(file_path: str) -> str:
    """
    Return a lightweight summary of classes/functions in a Python file.
    """
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return ""
    try:
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception:
        return ""

    lines: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            args = [a.arg for a in node.args.args]
            lines.append(f"def {node.name}({', '.join(args)}): ...")
        elif isinstance(node, ast.AsyncFunctionDef):
            args = [a.arg for a in node.args.args]
            lines.append(f"async def {node.name}({', '.join(args)}): ...")
        elif isinstance(node, ast.ClassDef):
            lines.append(f"class {node.name}: ...")
    return "\n".join(lines)


def build_context_chunks(target_file: str, related_files: List[str]) -> List[ContextChunk]:
    """
    Build context with full target file and summarized signatures for other files.
    """
    chunks: List[ContextChunk] = []
    seen = set()
    for f in related_files:
        if not f or f in seen:
            continue
        seen.add(f)
        p = Path(f)
        if not p.exists() or not p.is_file():
            continue
        if f == target_file:
            try:
                content = p.read_text(encoding="utf-8")
            except Exception:
                content = ""
        else:
            content = summarize_file_signatures(f)
        if content:
            chunks.append(ContextChunk(file_path=f, content=content))
    return chunks
