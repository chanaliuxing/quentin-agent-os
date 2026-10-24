from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict
import sys

# Allow direct script execution without editable install.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from quentin.observability.service import ObservabilityService
from quentin.diagnostics.intelligence_auditor import build_intelligence_audit


def _escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _get(d: Dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
    return cur if cur is not None else default


def _render_html(overview: Dict[str, Any]) -> str:
    ts = str(overview.get("timestamp") or datetime.now(UTC).isoformat())
    total_tasks = _get(overview, "domain.task.total_tasks", 0)
    mem_total = _get(overview, "memory.total_records", None)
    mem_hit = _get(overview, "memory.recall_hit_rate", None)
    exp_total = _get(overview, "experiments.total_experiments", None)
    patch_total = _get(overview, "patches.total_patches", None)
    planner_repair_rate = _get(overview, "intelligence.planner_repairs.repair_rate", None)
    blocked_repeat_ratio = _get(overview, "intelligence.blocked_action_recurrence.repeat_ratio", None)
    weak_resolution_rate = _get(overview, "intelligence.done_council_quality.weak_resolution_rate", None)
    discovery_compliance = _get(overview, "intelligence.planner_repairs.discovery_precheck.compliance_rate", None)
    recovery_success_rate = _get(overview, "intelligence.recovery_loop.success_rate", None)
    recovery_sample_size = _get(overview, "intelligence.recovery_loop.sample_size", 0)
    top_blocked = _get(overview, "intelligence.blocked_action_recurrence.top_actions", [])
    guessing_violations = _get(overview, "intelligence_audit.guessing_trap.risky_without_discovery", 0)
    strategy_fallbacks = _get(overview, "intelligence_audit.strategy_regression.fallback_decompositions", 0)
    repeated_blocked = _get(overview, "intelligence_audit.self_awareness_gap.blocked_action_repeated", 0)
    audit_top_repeated = _get(overview, "intelligence_audit.self_awareness_gap.top_repeated_actions", [])
    recovery_focus_breakdown = _get(overview, "intelligence.recovery_loop.focus_breakdown", [])

    data_json = json.dumps(overview, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Quentin Overview</title>
  <style>
    :root {{
      --bg: #0b1020;
      --panel: #111a33;
      --text: #e7ecff;
      --muted: rgba(231, 236, 255, 0.75);
      --border: rgba(231, 236, 255, 0.12);
      --accent: #6ee7ff;
      --good: #53ffa2;
      --warn: #ffd67a;
    }}
    html, body {{
      margin: 0;
      padding: 0;
      background: radial-gradient(1200px 600px at 20% 0%, rgba(110, 231, 255, 0.12), transparent 60%),
                  radial-gradient(900px 500px at 90% 10%, rgba(83, 255, 162, 0.10), transparent 55%),
                  var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
    }}
    .wrap {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 28px 20px 40px;
    }}
    header {{
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 0 18px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 18px;
    }}
    h1 {{
      font-size: 22px;
      margin: 0;
      letter-spacing: 0.3px;
    }}
    .ts {{
      font-size: 13px;
      color: var(--muted);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 12px;
    }}
    .card {{
      grid-column: span 3;
      background: linear-gradient(180deg, rgba(17, 26, 51, 0.9), rgba(17, 26, 51, 0.65));
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px 14px 12px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.22);
    }}
    .card h3 {{
      margin: 0 0 6px;
      font-size: 12px;
      color: var(--muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .val {{
      font-size: 26px;
      font-weight: 700;
      line-height: 1.1;
    }}
    .sub {{
      margin-top: 8px;
      font-size: 12px;
      color: var(--muted);
    }}
    .panel {{
      grid-column: span 12;
      background: rgba(17, 26, 51, 0.55);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      text-align: left;
      border-bottom: 1px solid var(--border);
      padding: 10px 8px;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-size: 11px;
    }}
    .pill {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid var(--border);
      color: var(--muted);
      font-size: 12px;
    }}
    @media (max-width: 900px) {{
      .card {{ grid-column: span 6; }}
    }}
    @media (max-width: 520px) {{
      .card {{ grid-column: span 12; }}
    }}
    .json {{
      white-space: pre-wrap;
      word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
      color: rgba(231, 236, 255, 0.85);
      background: rgba(0,0,0,0.25);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      margin: 0;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Quentin Overview</h1>
      <div class="ts">Generated at: {_escape(ts)}</div>
    </header>

    <div class="grid">
      <div class="card">
        <h3>Tasks</h3>
        <div class="val">{_escape(total_tasks)}</div>
        <div class="sub">From persisted traces</div>
      </div>
      <div class="card">
        <h3>Memory Records</h3>
        <div class="val">{_escape(mem_total if mem_total is not None else "n/a")}</div>
        <div class="sub">Recall hit rate: <span class="pill">{_escape(mem_hit if mem_hit is not None else "n/a")}</span></div>
      </div>
      <div class="card">
        <h3>Experiments</h3>
        <div class="val">{_escape(exp_total if exp_total is not None else "n/a")}</div>
        <div class="sub">Offline suite runs + promotions</div>
      </div>
      <div class="card">
        <h3>Patches</h3>
        <div class="val">{_escape(patch_total if patch_total is not None else "n/a")}</div>
        <div class="sub">PatchFlow + selfprog outputs</div>
      </div>
      <div class="card">
        <h3>Planner Repair Rate</h3>
        <div class="val">{_escape(f"{float(planner_repair_rate):.2f}" if planner_repair_rate is not None else "n/a")}</div>
        <div class="sub">Planning self-repair pressure</div>
      </div>
      <div class="card">
        <h3>Blocked Repeat Ratio</h3>
        <div class="val">{_escape(f"{float(blocked_repeat_ratio):.2f}" if blocked_repeat_ratio is not None else "n/a")}</div>
        <div class="sub">Guard feedback recurrence</div>
      </div>
      <div class="card">
        <h3>Done Weak Fix Rate</h3>
        <div class="val">{_escape(f"{float(weak_resolution_rate):.2f}" if weak_resolution_rate is not None else "n/a")}</div>
        <div class="sub">Council reasoning recovery</div>
      </div>
      <div class="card">
        <h3>Discovery Compliance</h3>
        <div class="val">{_escape(f"{float(discovery_compliance):.2f}" if discovery_compliance is not None else "n/a")}</div>
        <div class="sub">Precheck before risky steps</div>
      </div>
      <div class="card">
        <h3>Recovery Success</h3>
        <div class="val">{_escape(f"{float(recovery_success_rate):.2f}" if recovery_success_rate is not None else "n/a")}</div>
        <div class="sub">Sample size: {_escape(recovery_sample_size)}</div>
      </div>
      <div class="card">
        <h3>Guessing Violations</h3>
        <div class="val">{_escape(guessing_violations)}</div>
        <div class="sub">Risky plans lacking discovery</div>
      </div>
      <div class="card">
        <h3>Fallback Decompositions</h3>
        <div class="val">{_escape(strategy_fallbacks)}</div>
        <div class="sub">Single-step regression repairs</div>
      </div>
      <div class="card">
        <h3>Repeated Blocked</h3>
        <div class="val">{_escape(repeated_blocked)}</div>
        <div class="sub">Commands/tools denied repeatedly</div>
      </div>

      <div class="panel">
        <div style="display:flex; align-items:baseline; justify-content:space-between; gap:12px;">
          <h2 style="margin:0; font-size:14px; letter-spacing:0.02em;">Raw Overview JSON</h2>
          <span class="pill">Stable schema</span>
        </div>
        <pre class="json" id="overview-json"></pre>
      </div>
      <div class="panel">
        <div style="display:flex; align-items:baseline; justify-content:space-between; gap:12px;">
          <h2 style="margin:0; font-size:14px; letter-spacing:0.02em;">Top Blocked Actions</h2>
          <span class="pill">Intelligence</span>
        </div>
        <pre class="json">{_escape(json.dumps(top_blocked, ensure_ascii=False, indent=2))}</pre>
      </div>
      <div class="panel">
        <div style="display:flex; align-items:baseline; justify-content:space-between; gap:12px;">
          <h2 style="margin:0; font-size:14px; letter-spacing:0.02em;">Audit Repeated Blocked Actions</h2>
          <span class="pill">Metacognitive Auditor</span>
        </div>
        <pre class="json">{_escape(json.dumps(audit_top_repeated, ensure_ascii=False, indent=2))}</pre>
      </div>
      <div class="panel">
        <div style="display:flex; align-items:baseline; justify-content:space-between; gap:12px;">
          <h2 style="margin:0; font-size:14px; letter-spacing:0.02em;">Recovery Focus Breakdown</h2>
          <span class="pill">Self-Healing</span>
        </div>
        <pre class="json">{_escape(json.dumps(recovery_focus_breakdown, ensure_ascii=False, indent=2))}</pre>
      </div>
    </div>

    <script type="application/json" id="overview-data">{_escape(data_json)}</script>
    <script>
      const raw = document.getElementById('overview-data').textContent || '{{}}';
      let obj = {{}};
      try {{ obj = JSON.parse(raw); }} catch (e) {{ obj = {{ error: String(e) }}; }}
      document.getElementById('overview-json').textContent = JSON.stringify(obj, null, 2);
    </script>
  </div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a static HTML dashboard from ObservabilityService.get_overview().")
    parser.add_argument("--repo-root", default=".", help="Repository root for reading data/*.jsonl artifacts.")
    parser.add_argument("--out", default="data/observability/overview.html", help="Output HTML path.")
    args = parser.parse_args()

    svc = ObservabilityService(repo_root=args.repo_root)
    overview = asyncio.run(svc.get_overview())
    if not isinstance(overview.get("intelligence_audit"), dict):
        overview["intelligence_audit"] = build_intelligence_audit(repo_root=args.repo_root)
    html = _render_html(overview)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print("Wrote:", str(out_path))


if __name__ == "__main__":
    main()
