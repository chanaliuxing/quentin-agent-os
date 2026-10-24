from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from quentin.knowledge_graph.schema import NodeType
from quentin.knowledge_graph.service import GraphService


def _render_html(subgraph: Dict[str, Any]) -> str:
    payload = json.dumps(subgraph, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>Quentin Knowledge Graph Export</title>
    <style>
      body {{ font-family: ui-sans-serif, system-ui, -apple-system; margin: 24px; }}
      h1 {{ margin: 0 0 12px 0; font-size: 18px; }}
      .meta {{ color: #444; margin-bottom: 16px; }}
      table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
      th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
      th {{ background: #f6f6f6; }}
      code {{ background: #f2f2f2; padding: 1px 4px; border-radius: 4px; }}
    </style>
  </head>
  <body>
    <h1>Knowledge Graph Subgraph</h1>
    <div class="meta" id="meta"></div>

    <h2>Nodes</h2>
    <table id="nodes">
      <thead><tr><th>node_id</th><th>type</th><th>ref_id</th><th>title</th></tr></thead>
      <tbody></tbody>
    </table>

    <h2>Edges</h2>
    <table id="edges">
      <thead><tr><th>edge_id</th><th>src</th><th>dst</th><th>type</th><th>weight</th></tr></thead>
      <tbody></tbody>
    </table>

    <script>
      const subgraph = {payload};
      document.getElementById("meta").textContent =
        `root=${{(subgraph.meta && subgraph.meta.root_ref) ? subgraph.meta.root_ref.join(":") : "unknown"}} depth=${{(subgraph.meta && subgraph.meta.depth) || ""}}`;

      const nodesBody = document.querySelector("#nodes tbody");
      for (const n of (subgraph.nodes || [])) {{
        const tr = document.createElement("tr");
        tr.innerHTML = `<td><code>${{n.node_id}}</code></td><td>${{n.node_type}}</td><td>${{n.ref_id}}</td><td>${{(n.title || "").slice(0, 200)}}</td>`;
        nodesBody.appendChild(tr);
      }}

      const edgesBody = document.querySelector("#edges tbody");
      for (const e of (subgraph.edges || [])) {{
        const tr = document.createElement("tr");
        tr.innerHTML = `<td><code>${{e.edge_id}}</code></td><td><code>${{e.src_node_id}}</code></td><td><code>${{e.dst_node_id}}</code></td><td>${{e.edge_type}}</td><td>${{e.weight}}</td>`;
        edgesBody.appendChild(tr);
      }}
    </script>
  </body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--memory-id", required=True, help="memory_id to export (root node ref_id)")
    ap.add_argument("--depth", type=int, default=2, help="hop depth (default: 2)")
    ap.add_argument("--out-json", default="", help="output JSON path (default: data/kg_exports/<id>.json)")
    ap.add_argument("--out-html", default="", help="output HTML path (default: data/kg_exports/<id>.html)")
    args = ap.parse_args()

    out_dir = Path("data/kg_exports")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = Path(args.out_json) if args.out_json else (out_dir / f"{args.memory_id}.json")
    out_html = Path(args.out_html) if args.out_html else (out_dir / f"{args.memory_id}.html")

    svc = GraphService()
    subgraph = svc.export_subgraph((NodeType.MEMORY, str(args.memory_id)), depth=int(args.depth))

    out_json.write_text(json.dumps(subgraph, ensure_ascii=False, indent=2), encoding="utf-8")
    out_html.write_text(_render_html(subgraph), encoding="utf-8")

    print(str(out_json))
    print(str(out_html))


if __name__ == "__main__":
    main()

