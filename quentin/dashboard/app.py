from flask import Flask, jsonify, render_template
from pathlib import Path
import json

app = Flask(__name__, template_folder='templates')
repo_root = Path(__file__).resolve().parents[2]

from flask import Flask, jsonify, render_template
from pathlib import Path
import json
from collections import defaultdict

app = Flask(__name__, template_folder='templates')
repo_root = Path(__file__).resolve().parents[2]
DATA_DIR = repo_root / "data"

def get_domain_metrics():
    traces_dir = DATA_DIR / "traces"
    if not traces_dir.exists():
        return []

    domain_stats = defaultdict(lambda: {"success": 0, "total": 0, "latency": [], "cost": []})

    for trace_file in traces_dir.glob("*.jsonl"):
        with trace_file.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    trace = json.loads(line)
                    # This is a simplified assumption on trace structure.
                    # The actual structure might be more complex.
                    domain = trace.get("payload", {}).get("context", {}).get("domain", "general")
                    status = trace.get("payload", {}).get("status")
                    latency = trace.get("payload", {}).get("latency_sec")

                    domain_stats[domain]["total"] += 1
                    if status == "success":
                        domain_stats[domain]["success"] += 1
                    if latency is not None:
                        domain_stats[domain]["latency"].append(latency)
                    # Cost is not yet tracked in traces, so we'll leave it empty
                except json.JSONDecodeError:
                    continue

    metrics = []
    for domain, stats in domain_stats.items():
        metrics.append({
            "domain": domain,
            "success_rate": stats["success"] / stats["total"] if stats["total"] > 0 else 0,
            "error_rate": (stats["total"] - stats["success"]) / stats["total"] if stats["total"] > 0 else 0,
            "avg_latency": sum(stats["latency"]) / len(stats["latency"]) if stats["latency"] else 0,
            "avg_cost": 0, # Placeholder
        })
    return metrics

def get_memory_fabric_stats():
    # This would ideally use MemoryFabric.get_stats(), but for simplicity, we'll estimate
    tier_counts = {}
    for tier in ["STS", "MTS", "LTS"]:
        tier_file = DATA_DIR / "memory" / f"{tier}.jsonl"
        if tier_file.exists():
            with tier_file.open("r") as f:
                tier_counts[tier] = sum(1 for _ in f)
        else:
            tier_counts[tier] = 0
            
    return {
        "tier_counts": tier_counts,
        "hit_rate": 0, # Needs implementation
        "promotion_rate": 0, # Needs implementation
        "decay_rate": 0, # Needs implementation
    }

def get_self_programming_stats():
    proposals_dir = DATA_DIR / "patches" / "proposals"
    applied_dir = DATA_DIR / "patches" / "applied"

    patches_generated = len(list(proposals_dir.glob("*.json"))) if proposals_dir.exists() else 0
    patches_applied = len(list(applied_dir.glob("*.jsonl"))) if applied_dir.exists() else 0
    
    # These are harder to calculate and require parsing logs. Placeholder for now.
    pass_rate = 0
    rollback_rate = 0

    return {
        "patches_generated": patches_generated,
        "patches_applied": patches_applied,
        "pass_rate": pass_rate,
        "rollback_rate": rollback_rate,
    }

def get_experiment_stats():
    exp_dir = DATA_DIR / "research" / "experiments"
    total_experiments = len(list(exp_dir.glob("*.json"))) if exp_dir.exists() else 0
    
    # Placeholder
    completed_experiments = 0
    pass_rate = 0
    
    return {
        "total_experiments": total_experiments,
        "completed_experiments": completed_experiments,
        "pass_rate": pass_rate,
    }


def get_real_metrics():
    """
    Gathers and aggregates real metrics from the data directory.
    """
    return {
        "domain_metrics": get_domain_metrics(),
        "memory_fabric_stats": get_memory_fabric_stats(),
        "self_programming_stats": get_self_programming_stats(),
        "experiment_stats": get_experiment_stats(),
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/metrics')
def api_metrics():
    metrics = get_real_metrics()
    return jsonify(metrics)

if __name__ == '__main__':
    app.run(debug=True, port=5001)
