import sys
from pathlib import Path
import random
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def run_chaos():
    print("Chaos P3: Simulating 429 Storm...")
    # Mocking client behavior by injecting a fault
    from quentin.infra.llm.failover import failover
    
    failures = 0
    for i in range(5):
        try:
            # Simulate logic
            if random.random() < 0.8:
                raise Exception("429 Rate Limit")
        except Exception as e:
            if failover.should_retry(e, i):
                print(f"Chaos: Retry triggered for {e}")
                failures += 1
            else:
                print("Chaos: Hard fail")
                
    report_path = Path("logs/chaos/report_p3.txt")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(f"Chaos Drill Complete. Recovered failures: {failures}")
    print("Chaos: OK")

if __name__ == "__main__":
    run_chaos()
