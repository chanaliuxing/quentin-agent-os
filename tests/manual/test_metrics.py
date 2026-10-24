import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quentin.infra.observability.metrics import MetricsCollector

def test_metrics():
    print("Testing Metrics...")
    repo_root = "."
    mc = MetricsCollector(repo_root=repo_root)
    
    initial_tokens = mc.data.get("tokens", 0)
    
    mc.record_usage(100, 0.05)
    
    data = json.loads(mc.stats_path.read_text())
    if data["tokens"] == initial_tokens + 100:
        print("Metrics: OK")
    else:
        raise ValueError(f"Incremental mismatch: {data['tokens']} != {initial_tokens} + 100")

if __name__ == "__main__":
    test_metrics()
