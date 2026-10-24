-- Enable extensions (idempotent)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Add pgvector column for embeddings
ALTER TABLE IF EXISTS memories
    ADD COLUMN IF NOT EXISTS vector_emb vector;

-- Indexes
CREATE INDEX IF NOT EXISTS memories_content_trgm ON memories USING gin (content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS memories_vector_emb_idx ON memories USING ivfflat (vector_emb) WITH (lists = 100);
