from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import hashlib


@dataclass(frozen=True)
class CodeChunk:
    chunk_id: str
    content: str
    metadata: Dict[str, Any]


def iter_python_files(
    *,
    repo_root: str | Path,
    package_dirs: Sequence[str] = ("quentin",),
    exclude_dir_names: Sequence[str] = (
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        "node_modules",
        "dist",
        "build",
        "site-packages",
        "data",
        "logs",
    ),
) -> Iterable[Path]:
    root = Path(repo_root).resolve()
    exclude = set(exclude_dir_names)
    for pkg in package_dirs:
        pkg_path = (root / pkg).resolve()
        if not pkg_path.exists():
            continue
        for path in pkg_path.rglob("*.py"):
            if any(part in exclude for part in path.parts):
                continue
            yield path


def _module_path_from_file(*, repo_root: Path, file_path: Path) -> str:
    rel = file_path.resolve().relative_to(repo_root.resolve())
    if rel.suffix == ".py":
        rel = rel.with_suffix("")
    return ".".join(rel.parts)


def _safe_docstring(node: ast.AST) -> Optional[str]:
    try:
        return ast.get_docstring(node)
    except Exception:
        return None


def _format_func_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    # Minimal "human readable" signature without type details.
    args = []
    for a in node.args.posonlyargs:
        args.append(a.arg)
    if node.args.posonlyargs:
        args.append("/")
    for a in node.args.args:
        args.append(a.arg)
    if node.args.vararg is not None:
        args.append("*" + node.args.vararg.arg)
    elif node.args.kwonlyargs:
        args.append("*")
    for a in node.args.kwonlyargs:
        args.append(a.arg)
    if node.args.kwarg is not None:
        args.append("**" + node.args.kwarg.arg)
    return f"def {node.name}({', '.join(args)}):"


def _format_class_signature(node: ast.ClassDef) -> str:
    bases = []
    for b in node.bases:
        try:
            bases.append(ast.unparse(b))
        except Exception:
            bases.append("Base")
    if bases:
        return f"class {node.name}({', '.join(bases)}):"
    return f"class {node.name}:"


def _stable_chunk_id(*, module_path: str, qualname: str, content: str) -> str:
    h = hashlib.sha1()
    h.update(module_path.encode("utf-8"))
    h.update(b"::")
    h.update(qualname.encode("utf-8"))
    h.update(b"::")
    h.update(content.encode("utf-8"))
    return f"code::{module_path}::{qualname}::{h.hexdigest()[:12]}"


def extract_code_chunks(
    *,
    repo_root: str | Path,
    file_path: str | Path,
    include_methods: bool = True,
) -> List[CodeChunk]:
    root = Path(repo_root).resolve()
    path = Path(file_path).resolve()
    module_path = _module_path_from_file(repo_root=root, file_path=path)
    rel_path = str(path.relative_to(root))

    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)

    chunks: List[CodeChunk] = []

    def _add(kind: str, name: str, qualname: str, signature: str, docstring: Optional[str], lineno: int) -> None:
        content_lines = [signature]
        if docstring:
            content_lines.append('"""')
            content_lines.append(docstring.strip())
            content_lines.append('"""')
        content = "\n".join(content_lines).strip() + "\n"
        chunk_id = _stable_chunk_id(module_path=module_path, qualname=qualname, content=content)
        chunks.append(
            CodeChunk(
                chunk_id=chunk_id,
                content=content,
                metadata={
                    "file_path": rel_path,
                    "module": module_path,
                    "kind": kind,
                    "name": name,
                    "fully_qualified_name": f"{module_path}:{qualname}",
                    "qualname": qualname,
                    "signature": signature,
                    "docstring": docstring,
                    "lineno": int(lineno),
                },
            )
        )

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            signature = _format_func_signature(node)
            _add(
                kind="function",
                name=node.name,
                qualname=node.name,
                signature=signature,
                docstring=_safe_docstring(node),
                lineno=getattr(node, "lineno", 1),
            )
        elif isinstance(node, ast.ClassDef):
            class_sig = _format_class_signature(node)
            _add(
                kind="class",
                name=node.name,
                qualname=node.name,
                signature=class_sig,
                docstring=_safe_docstring(node),
                lineno=getattr(node, "lineno", 1),
            )
            if include_methods:
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        signature = _format_func_signature(child)
                        qual = f"{node.name}.{child.name}"
                        _add(
                            kind="method",
                            name=child.name,
                            qualname=qual,
                            signature=signature,
                            docstring=_safe_docstring(child),
                            lineno=getattr(child, "lineno", getattr(node, "lineno", 1)),
                        )

    return chunks


async def index_codebase_to_vector_store(
    *,
    repo_root: str | Path,
    vector_store: Any,
    package_dirs: Sequence[str] = ("quentin",),
    reset: bool = False,
    max_files: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Index Python symbols into the provided `vector_store` (ChromaVectorStore or compatible).

    Returns summary stats without writing any repo-tracked artifacts.
    """
    root = Path(repo_root).resolve()

    if reset and hasattr(vector_store, "reset"):
        vector_store.reset()

    files = list(iter_python_files(repo_root=root, package_dirs=package_dirs))
    if max_files is not None:
        files = files[: int(max_files)]

    saved = 0
    errors: List[Tuple[str, str]] = []
    for path in files:
        try:
            chunks = extract_code_chunks(repo_root=root, file_path=path)
            for ch in chunks:
                await vector_store.save(ch.chunk_id, ch.content, ch.metadata)
                saved += 1
        except Exception as e:  # noqa: BLE001
            errors.append((str(path), repr(e)))
            continue

    return {
        "files_indexed": len(files),
        "chunks_saved": saved,
        "errors": errors,
    }

