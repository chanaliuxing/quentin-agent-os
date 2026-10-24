from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import json

from quentin.infra.storage.vector_store import ChromaVectorStore, NullVectorStore
from quentin.retrieval.codebase_index import index_codebase_to_vector_store


def main() -> int:
    p = argparse.ArgumentParser(description="Index codebase symbols into ChromaDB for RAG/tooling.")
    p.add_argument("--repo-root", default=".", help="Repository root (default: .)")
    p.add_argument("--package", action="append", default=["quentin"], help="Package dir to index (repeatable)")
    p.add_argument("--db-path", default="chroma_db_code_chunks", help="Chroma persistent db path")
    p.add_argument("--reset", action="store_true", help="Reset Chroma collection before indexing")
    p.add_argument("--max-files", type=int, default=None, help="Limit number of files (debugging)")
    p.add_argument("--out", default=None, help="Optional JSON output path for summary")
    args = p.parse_args()

    repo_root = Path(args.repo_root).resolve()
    try:
        store = ChromaVectorStore(db_path=args.db_path)
    except Exception:
        store = NullVectorStore()

    summary = asyncio.run(
        index_codebase_to_vector_store(
            repo_root=repo_root,
            vector_store=store,
            package_dirs=tuple(args.package),
            reset=bool(args.reset),
            max_files=args.max_files,
        )
    )

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

