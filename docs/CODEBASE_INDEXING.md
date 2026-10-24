# Codebase Indexing (RAG / Skill Context)

This repo includes a lightweight codebase indexer that chunks Python symbols (functions/classes/methods) and stores them in ChromaDB for later retrieval (e.g. self-programming `_build_skill_context_for_gap`).

## What It Indexes

- Scope: by default, `quentin/` Python files.
- Chunking: one chunk per top-level function/class, plus class methods.
- Content: signature + docstring (docstring is the main semantic payload).
- Metadata: includes `file_path`, `module`, `fully_qualified_name`, `signature`, and `docstring`.

## How To Run

```bash
python scripts/index_codebase.py --reset
```

Common options:

```bash
python scripts/index_codebase.py --db-path chroma_db_code_chunks --package quentin
python scripts/index_codebase.py --max-files 200
python scripts/index_codebase.py --out data/index_summary.json
```

## Where It Is Used

- Indexer: `quentin/retrieval/codebase_index.py`
- CLI script: `scripts/index_codebase.py`
- Consumer (example): `meta_agent/self_programming/engine_v2.py` uses `vector_store.search(...)` to build skill/tool context for a gap.

