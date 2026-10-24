-- migrations/0002_knowledge_graph.sql
-- This migration script creates the tables for the knowledge graph.

CREATE TABLE IF NOT EXISTS kg_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    ref_id TEXT NOT NULL,
    title TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(node_type, ref_id)
);

CREATE INDEX IF NOT EXISTS idx_kg_nodes_ref ON kg_nodes(ref_id);

CREATE TABLE IF NOT EXISTS kg_edges (
    edge_id TEXT PRIMARY KEY,
    src_node_id TEXT REFERENCES kg_nodes(node_id),
    dst_node_id TEXT REFERENCES kg_nodes(node_id),
    edge_type TEXT NOT NULL,
    weight DOUBLE PRECISION DEFAULT 1.0,
    evidence JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(src_node_id, dst_node_id, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_kg_edges_src ON kg_edges(src_node_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_dst ON kg_edges(dst_node_id);
