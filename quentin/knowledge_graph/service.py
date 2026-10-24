# quentin/knowledge_graph/service.py
from __future__ import annotations
import uuid
import logging
import os
from typing import Optional, List, Dict, Any, Set, Tuple

from .schema import NodeType, EdgeType, KGNode, KGEdge
from .store import PostgresGraphStore, NullGraphStore, GraphStore
from .store_file import FileGraphStore
from meta_agent.runtime import council

logger = logging.getLogger(__name__)

class GraphService:
    def __init__(self, store: Optional[GraphStore] = None):
        self.store = store or self._bootstrap_store()
        try:
            self.store.init_schema()
        except Exception as e:
            logger.warning(f"Graph schema init failed (likely already exists or connection error): {e}")
            if not isinstance(self.store, NullGraphStore):
                logger.warning("Falling back to NullGraphStore after init failure.")
                self.store = NullGraphStore()

    def _bootstrap_store(self) -> GraphStore:
        kind = (os.getenv("QUENTIN_GRAPH_STORE") or "").strip().lower()
        # Blueprint v3 expectation: default environment should not silently disable KG.
        # Use a local file-backed store by default; require an explicit opt-out to disable.
        if kind in ("disabled", "off", "0", "false", "none", "null"):
            return NullGraphStore()
        if kind in ("", "file"):
            return FileGraphStore()
        if kind not in ("postgres",):
            logger.warning("Unknown QUENTIN_GRAPH_STORE=%r; disabling graph store.", kind)
            return NullGraphStore()

        try:
            return PostgresGraphStore()
        except Exception as e:
            logger.warning(
                "PostgresGraphStore unavailable, falling back to NullGraphStore (graph features disabled): %s", e
            )
            return NullGraphStore()

    # -------- Query helpers --------
    def get_neighbors(self, node_id: str, depth: int = 1, direction: str = "out") -> Dict[str, Any]:
        """
        Traverse neighbors up to a given depth (both in/out if direction='both').
        Returns a subgraph dict with nodes and edges encountered.
        """
        if depth <= 0:
            return {"nodes": [], "edges": []}

        seen_nodes: Set[str] = set([node_id])
        nodes: Dict[str, Dict] = {}
        edges: List[Dict] = []
        frontier: List[Tuple[str, int]] = [(node_id, 0)]

        while frontier:
            current, d = frontier.pop(0)
            if d >= depth:
                continue

            dirs = [direction] if direction != "both" else ["out", "in"]
            for dirn in dirs:
                try:
                    neighs = self.store.get_neighbors(current, direction=dirn)
                except Exception as e:
                    logger.warning(f"get_neighbors failed for {current}/{dirn}: {e}")
                    continue
                for row in neighs:
                    edges.append(row)
                    nid = row["node_id"]
                    if nid not in seen_nodes:
                        seen_nodes.add(nid)
                        nodes[nid] = row
                        frontier.append((nid, d + 1))

        return {
            "nodes": list(nodes.values()),
            "edges": edges,
        }

    async def explain_link(self, src_ref: tuple[NodeType, str], dst_ref: tuple[NodeType, str], max_depth: int = 3, use_llm: bool = False) -> Dict[str, Any]:
        """
        Lightweight path search between two nodes with a human-readable summary.
        If use_llm=True, uses LLM to provide a narrative explanation of the path.
        """
        src_node = self.store.get_node_by_ref(src_ref[0], src_ref[1])
        dst_node = self.store.get_node_by_ref(dst_ref[0], dst_ref[1])
        if not src_node or not dst_node:
            return {"error": "source_or_dest_missing"}

        path = self._bfs_path(src_node.node_id, dst_node.node_id, max_depth=max_depth)
        if not path:
            return {"error": "no_path_found"}

        summary_parts = []
        for step in path:
            src_node_step = self.store.get_node_by_id(step["src_node_id"])
            dst_node_step = self.store.get_node_by_id(step["dst_node_id"])
            src_label = src_node_step.title or src_node_step.ref_id if src_node_step else step["src_node_id"]
            dst_label = dst_node_step.title or dst_node_step.ref_id if dst_node_step else step["dst_node_id"]
            summary_parts.append(
                f"{src_label} --{step['edge_type']}--> {dst_label}"
            )
        summary = " | ".join(summary_parts)

        if use_llm:
            try:
                question = "Explain the following path in the knowledge graph in a natural, meaningful way."
                context = {
                    "source": src_node.title or src_node.ref_id,
                    "destination": dst_node.title or dst_node.ref_id,
                    "path_raw": summary,
                    "path_details": path
                }
                narrative = await council.ask_json(
                    role="graph_expert",
                    question=question,
                    context=context,
                    json_schema_hint="{\"explanation\": \"string\"}"
                )
                return {"path": path, "summary": summary, "narrative": narrative.get("explanation")}
            except Exception as e:
                logger.warning(f"LLM explain_link failed: {e}")

        return {"path": path, "summary": summary}

    def export_subgraph(self, root_ref: tuple[NodeType, str], depth: int = 2, format: str = "json") -> Any:
        """
        Export a subgraph rooted at a given ref_id up to depth.
        Supported formats: json (default), graphml
        """
        root = self.store.get_node_by_ref(root_ref[0], root_ref[1])
        if not root:
            return {"nodes": [], "edges": [], "meta": {"root_ref": [root_ref[0].value, root_ref[1]], "depth": depth}}

        raw = self.get_neighbors(root.node_id, depth=depth, direction="both")
        nodes_raw = raw.get("nodes") or []
        edges_raw = raw.get("edges") or []

        nodes: Dict[str, Dict[str, Any]] = {}
        nodes[root.node_id] = {
            "node_id": root.node_id,
            "node_type": root.node_type.value,
            "ref_id": root.ref_id,
            "title": root.title,
        }
        for n in nodes_raw:
            node_id = n.get("node_id")
            if not node_id: continue
            nodes[str(node_id)] = {
                "node_id": str(node_id),
                "node_type": str(n.get("node_type") or ""),
                "ref_id": str(n.get("ref_id") or ""),
                "title": str(n.get("title") or ""),
            }

        edges: List[Dict[str, Any]] = []
        for e in edges_raw:
            edges.append({
                "edge_id": str(e.get("edge_id") or ""),
                "src_node_id": str(e.get("src_node_id") or ""),
                "dst_node_id": str(e.get("dst_node_id") or ""),
                "edge_type": str(e.get("edge_type") or ""),
                "weight": float(e.get("weight") or 1.0),
            })

        if format == "graphml":
            return self._to_graphml(list(nodes.values()), edges)

        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "meta": {"root_ref": [root_ref[0].value, root_ref[1]], "depth": depth},
        }

    def _to_graphml(self, nodes: List[Dict], edges: List[Dict]) -> str:
        """ Lightweight GraphML generation. """
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
            '  <key id="d0" for="node" attr.name="node_type" attr.type="string"/>',
            '  <key id="d1" for="node" attr.name="ref_id" attr.type="string"/>',
            '  <key id="d2" for="node" attr.name="title" attr.type="string"/>',
            '  <key id="d3" for="edge" attr.name="edge_type" attr.type="string"/>',
            '  <graph id="G" edgedefault="directed">'
        ]
        
        for n in nodes:
            nid = n['node_id']
            lines.append(f'    <node id="{nid}">')
            lines.append(f'      <data key="d0">{n["node_type"]}</data>')
            lines.append(f'      <data key="d1">{n["ref_id"]}</data>')
            lines.append(f'      <data key="d2">{n["title"]}</data>')
            lines.append( '    </node>')
            
        for e in edges:
            lines.append(f'    <edge id="{e["edge_id"]}" source="{e["src_node_id"]}" target="{e["dst_node_id"]}">')
            lines.append(f'      <data key="d3">{e["edge_type"]}</data>')
            lines.append( '    </edge>')
            
        lines.append('  </graph>')
        lines.append('</graphml>')
        return "\n".join(lines)

    # -------- Internal helpers --------
    def _bfs_path(self, src_id: str, dst_id: str, max_depth: int = 3) -> List[Dict[str, Any]]:
        from collections import deque

        queue = deque([(src_id, [])])
        seen = set([src_id])
        while queue:
            node, path = queue.popleft()
            if len(path) // 2 >= max_depth:
                continue
            for dirn in ("out", "in"):
                try:
                    neighs = self.store.get_neighbors(node, direction=dirn)
                except Exception:
                    continue
                for row in neighs:
                    next_id = row["dst_node_id"] if dirn == "out" else row["src_node_id"]
                    if next_id in seen:
                        continue
                    seen.add(next_id)
                    new_path = path + [row]
                    if next_id == dst_id:
                        return new_path
                    queue.append((next_id, new_path))
        return []

    def sync_node(self, type: NodeType, ref_id: str, title: str = "", meta: dict = None) -> str:
        """
        Idempotent sync of a node. Returns the internal node_id.
        """
        node = KGNode(
            node_id=str(uuid.uuid4()), # Will only be used on insert
            node_type=type,
            ref_id=ref_id,
            title=title,
            metadata=meta or {}
        )
        return self.store.upsert_node(node)

    def create_link(self, src_ref: tuple[NodeType, str], dst_ref: tuple[NodeType, str], rel: EdgeType, weight=1.0):
        """
        High-level link creation using ref_ids (e.g. memory_id).
        Auto-creates nodes if they don't exist.
        src_ref = (NodeType.MEMORY, "mem_123")
        """
        src_id = self.sync_node(src_ref[0], src_ref[1])
        dst_id = self.sync_node(dst_ref[0], dst_ref[1])
        
        edge = KGEdge.new(src_id, dst_id, rel, weight)
        self.store.upsert_edge(edge)
        return edge.edge_id

    def explain_provenance(self, ref_id: str, node_type: NodeType = NodeType.MEMORY) -> Dict[str, Any]:
        """
        Returns "Where did this come from?"
        """
        node = self.store.get_node_by_ref(node_type, ref_id)
        if not node:
            return {"error": "Node not found"}
            
        # Get incoming edges (sources)
        sources = self.store.get_neighbors(node.node_id, direction="in")
        
        provenance = {
            "node": node.title or node.ref_id,
            "sources": []
        }
        
        for row in sources:
            provenance["sources"].append({
                "type": row['edge_type'],
                "source_node": row['title'] or row['ref_id'],
                "source_type": row['node_type'],
                "ref_id": row['ref_id']
            })
            
        return provenance

    async def query_by_intent(self, intent: str, max_results: int = 5) -> Dict[str, Any]:
        """
        Advanced Query: Find relevant knowledge graph nodes by high-level intent.
        1. Uses LLM to identify potential starting ref_ids or keywords.
        2. Probes the graph for neighbors and related concepts.
        """
        try:
            question = f"Based on the intent '{intent}', identify 3-5 relevant concept IDs or tool names that might exist in our knowledge graph."
            context = {"intent": intent}
            hints = await council.ask_json(
                role="graph_analyst",
                question=question,
                context=context,
                json_schema_hint="{\"candidates\": [{\"ref_id\": \"string\", \"type\": \"string\", \"reason\": \"string\"}]}"
            )
            
            results = []
            for cand in hints.get("candidates", []):
                # Try to find the node
                n_type_str = str(cand.get("type", "concept")).lower()
                try:
                    n_type = NodeType(n_type_str)
                except:
                    n_type = NodeType.CONCEPT
                    
                node = self.store.get_node_by_ref(n_type, cand["ref_id"])
                if node:
                    # Get immediate neighbors for context
                    neighbors = self.get_neighbors(node.node_id, depth=1)
                    results.append({
                        "node": {
                            "ref_id": node.ref_id,
                            "title": node.title,
                            "type": node.node_type.value,
                            "reason": cand.get("reason")
                        },
                        "context": neighbors
                    })
            
            return {"intent": intent, "results": results[:max_results]}
        except Exception as e:
            logger.error(f"query_by_intent failed: {e}")
            return {"error": str(e)}
