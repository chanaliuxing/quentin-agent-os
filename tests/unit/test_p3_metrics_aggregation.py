import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quentin.observability.p3_metrics import p3_metrics

def test_metrics():
    p3_metrics.record("latency", 100)
    p3_metrics.record("latency", 200)
    p3_metrics.record("latency", 300)
    
    snap = p3_metrics.snapshot()
    assert snap["latency_count"] == 3
    assert snap["latency_avg"] == 200.0
    print("P3Metrics: OK")

if __name__ == "__main__":
    test_metrics()
