from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Dict, List


def _stable_code(text: str) -> str:
    return "\n".join((text or "").strip().splitlines()).strip()


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _python_function_fingerprints(content: str) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    try:
        tree = ast.parse(content or "")
    except Exception:
        return out

    lines = (content or "").splitlines()
    class_stack: List[str] = []

    def _walk(node: ast.AST) -> None:
        nonlocal out, class_stack
        if isinstance(node, ast.ClassDef):
            class_stack.append(str(getattr(node, "name", "") or ""))
            for child in node.body:
                _walk(child)
            class_stack.pop()
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = str(getattr(node, "name", "") or "")
            lineno = int(getattr(node, "lineno", 0) or 0)
            end_lineno = int(getattr(node, "end_lineno", lineno) or lineno)
            if not name or lineno <= 0 or end_lineno < lineno:
                return
            src = "\n".join(lines[lineno - 1 : end_lineno])
            stable = _stable_code(src)
            qualname = ".".join([*([x for x in class_stack if x]), name]) if class_stack else name
            # AST semantic fingerprint to reduce formatting sensitivity.
            semantic = ast.dump(node, include_attributes=False)
            out.append(
                {
                    "name": name,
                    "qualname": qualname,
                    "start_line": lineno,
                    "end_line": end_lineno,
                    "fingerprint": _sha(stable),
                    "semantic_fingerprint": _sha(semantic),
                    "kind": "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                }
            )
            return
        for child in ast.iter_child_nodes(node):
            _walk(child)

    _walk(tree)
    out.sort(key=lambda x: (str(x.get("name") or ""), int(x.get("start_line") or 0)))
    return out


def _js_like_function_fingerprints(content: str) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    lines = (content or "").splitlines()
    pat_function = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\(")
    pat_arrow = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{")
    pat_method = re.compile(r"^\s*(?:async\s+)?([A-Za-z_]\w*)\s*\([^)]*\)\s*\{")

    def _extract_block(start_idx: int) -> tuple[int, str]:
        depth = 0
        buf: List[str] = []
        end_idx = start_idx
        started = False
        for i in range(start_idx, len(lines)):
            line = lines[i]
            buf.append(line)
            opens = line.count("{")
            closes = line.count("}")
            if opens > 0:
                started = True
            depth += opens
            depth -= closes
            if started and depth <= 0:
                end_idx = i
                break
        return end_idx + 1, "\n".join(buf)

    for i, line in enumerate(lines):
        m = pat_function.search(line) or pat_arrow.search(line)
        kind = "function"
        if m is None:
            # Class-like method (best-effort)
            m = pat_method.search(line)
            kind = "method"
        if m is None:
            continue
        name = str(m.group(1) or "")
        if not name:
            continue
        end_line, body = _extract_block(i)
        stable = _stable_code(body or line)
        out.append(
            {
                "name": name,
                "start_line": i + 1,
                "end_line": end_line,
                "fingerprint": _sha(stable),
                "kind": kind,
            }
        )
    return out


def build_code_function_fingerprints(*, file_path: str | Path, content: str) -> List[Dict[str, object]]:
    suffix = str(Path(file_path).suffix or "").lower()
    if suffix == ".py":
        return _python_function_fingerprints(content)
    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        return _js_like_function_fingerprints(content)
    return []


def build_function_fingerprint_hash(
    fingerprints: List[Dict[str, object]],
    *,
    position_insensitive: bool = True,
) -> str:
    if not fingerprints:
        return ""
    normalized: List[str] = []
    for item in fingerprints:
        name = str(item.get("qualname") or item.get("name") or "")
        fp = str(item.get("semantic_fingerprint") or item.get("fingerprint") or "")
        if not fp:
            continue
        if position_insensitive:
            normalized.append(f"{name}:{fp}")
        else:
            start = int(item.get("start_line") or 0)
            end = int(item.get("end_line") or 0)
            normalized.append(f"{name}:{start}:{end}:{fp}")
    if not normalized:
        return ""
    normalized.sort()
    return _sha("|".join(normalized))
