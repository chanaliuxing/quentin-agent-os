# quentin/knowledge_graph/store.py
from __future__ import annotations
import os
import json
from typing import List, Optional, Dict, Any, Protocol
import logging

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None

from .schema import KGNode, KGEdge, NodeType, EdgeType

logger = logging.getLogger(__name__)


class GraphStore(Protocol):
    def init_schema(self): ...
    def upsert_node(self, node: "KGNode") -> str: ...
    def upsert_edge(self, edge: "KGEdge"): ...
    def get_node_by_ref(self, node_type: "NodeType", ref_id: str) -> Optional["KGNode"]: ...
    def get_node_by_id(self, node_id: str) -> Optional["KGNode"]: ...
    def get_neighbors(self, node_id: str, edge_type: Optional["EdgeType"] = None, direction: str = "out") -> List[Dict]: ...


class PostgresGraphStore:
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv("PG_DSN") or self._env_pg_dsn()
        if not self.dsn:
            raise ValueError("PostgresGraphStore requires DSN or PG_* env vars.")
        self._conn = None

    def _env_pg_dsn(self) -> Optional[str]:
        host = os.getenv("PG_HOST")
        if not host: return None
        return f"postgresql://{os.getenv('PG_USER','postgres')}:{os.getenv('PG_PASSWORD','')}@{host}:{os.getenv('PG_PORT','5432')}/{os.getenv('PG_DB','postgres')}"

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self.dsn, row_factory=dict_row, autocommit=False)
        return self._conn

    def init_schema(self):
        """Idempotent schema creation."""
        with self.conn.cursor() as cur:
            # Clean up stray composite types if tables don't exist (avoids duplicate typname errors).
            cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'kg_nodes' AND relkind = 'r') THEN
                    IF EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                               WHERE t.typname = 'kg_nodes' AND n.nspname = current_schema()) THEN
                        DROP TYPE kg_nodes;
                    END IF;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'kg_edges' AND relkind = 'r') THEN
                    IF EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                               WHERE t.typname = 'kg_edges' AND n.nspname = current_schema()) THEN
                        DROP TYPE kg_edges;
                    END IF;
                END IF;
            END $$;
            """)

            cur.execute("""
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
            """)
            self.conn.commit()

    def upsert_node(self, node: KGNode) -> str:
        """Returns node_id. Creates if not exists, updates metadata if exists."""
        sql = """
        INSERT INTO kg_nodes (node_id, node_type, ref_id, title, metadata)
        VALUES (%(id)s, %(type)s, %(ref)s, %(title)s, %(meta)s)
        ON CONFLICT (node_type, ref_id) 
        DO UPDATE SET 
            metadata = kg_nodes.metadata || EXCLUDED.metadata,
            title = COALESCE(EXCLUDED.title, kg_nodes.title),
            updated_at = NOW()
        RETURNING node_id;
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, {
                "id": node.node_id,
                "type": node.node_type.value,
                "ref": node.ref_id,
                "title": node.title,
                "meta": json.dumps(node.metadata)
            })
            return cur.fetchone()['node_id']

    def upsert_edge(self, edge: KGEdge):
        sql = """
        INSERT INTO kg_edges (edge_id, src_node_id, dst_node_id, edge_type, weight, evidence)
        VALUES (%(id)s, %(src)s, %(dst)s, %(type)s, %(w)s, %(ev)s)
        ON CONFLICT (src_node_id, dst_node_id, edge_type)
        DO UPDATE SET
            weight = EXCLUDED.weight,
            evidence = kg_edges.evidence || EXCLUDED.evidence;
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, {
                "id": edge.edge_id,
                "src": edge.src_node_id,
                "dst": edge.dst_node_id,
                "type": edge.edge_type.value,
                "w": edge.weight,
                "ev": json.dumps(edge.evidence)
            })
        self.conn.commit()

    def get_node_by_ref(self, node_type: NodeType, ref_id: str) -> Optional[KGNode]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM kg_nodes WHERE node_type = %s AND ref_id = %s", (node_type.value, ref_id))
            row = cur.fetchone()
            if row:
                return self._row_to_node(row)
        return None

    def get_node_by_id(self, node_id: str) -> Optional[KGNode]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM kg_nodes WHERE node_id = %s", (node_id,))
            row = cur.fetchone()
            if row:
                return self._row_to_node(row)
        return None

    def get_neighbors(self, node_id: str, edge_type: Optional[EdgeType] = None, direction="out") -> List[Dict]:
        """Simple 1-hop neighbor query."""
        if direction == "out":
            sql = "SELECT e.*, n.* FROM kg_edges e JOIN kg_nodes n ON e.dst_node_id = n.node_id WHERE e.src_node_id = %s"
        else:
            sql = "SELECT e.*, n.* FROM kg_edges e JOIN kg_nodes n ON e.src_node_id = n.node_id WHERE e.dst_node_id = %s"
        
        params = [node_id]
        if edge_type:
            sql += " AND e.edge_type = %s"
            params.append(edge_type.value)
            
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def _row_to_node(self, row) -> KGNode:
        return KGNode(
            node_id=row['node_id'],
            node_type=NodeType(row['node_type']),
            ref_id=row['ref_id'],
            title=row['title'],
            metadata=row['metadata'],
            created_at=row['created_at']
        )


class NullGraphStore:
    """No-op graph store to allow running without Postgres."""

    def init_schema(self):
        return None

    def upsert_node(self, node: KGNode) -> str:
        return node.node_id

    def upsert_edge(self, edge: KGEdge):
        return edge.edge_id

    def get_node_by_ref(self, node_type: NodeType, ref_id: str) -> Optional[KGNode]:
        return None

    def get_node_by_id(self, node_id: str) -> Optional[KGNode]:
        return None

    def get_neighbors(self, node_id: str, edge_type: Optional[EdgeType] = None, direction: str = "out") -> List[Dict]:
        return []
