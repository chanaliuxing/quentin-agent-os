#!/usr/bin/env python3
import json
import os
import time
import argparse
from typing import List, Dict, Any

def main():
    parser = argparse.ArgumentParser(description="Analyze LLM raw history logs.")
    parser.add_argument("--minutes", type=int, default=60, help="Analyze logs from the last N minutes.")
    parser.add_argument("--output", type=str, default="logs/qa/llm_raw_history_report.json", help="Report output path.")
    args = parser.parse_args()

    log_path = "data/llm_raw_history.jsonl"
    if not os.path.exists(log_path):
        print(f"Log file not found: {log_path}")
        return

    now = time.time()
    threshold = now - (args.minutes * 60)
    
    entries = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("ts", 0) >= threshold:
                    entries.append(entry)
            except Exception:
                continue

    if not entries:
        print(f"No log entries found in the last {args.minutes} minutes.")
        return

    report = {
        "summary": {
            "total_calls": len(entries),
            "success_rate": sum(1 for e in entries if e.get("ok")) / len(entries),
            "analyze_window_minutes": args.minutes,
            "timestamp": now
        },
        "latency": {},
        "errors": [],
        "blobs_check": []
    }

    # Latency by actor
    actor_latencies = {}
    for e in entries:
        actor = e.get("actor", "unknown")
        actor_latencies.setdefault(actor, []).append(e.get("latency_ms", 0))
    
    for actor, latencies in actor_latencies.items():
        latencies.sort()
        report["latency"][actor] = {
            "p50": latencies[len(latencies)//2],
            "p95": latencies[int(len(latencies)*0.95)],
            "max": max(latencies),
            "count": len(latencies)
        }

    # Error check
    for e in entries:
        if not e.get("ok"):
            report["errors"].append({
                "ts": e.get("ts"),
                "actor": e.get("actor"),
                "model": e.get("model"),
                "error": e.get("error"),
                "error_response_body": e.get("error_response_body")
            })

    # Blobs check
    for e in entries:
        ref = e.get("raw_response_ref")
        if ref:
            path = ref.get("path")
            exists = os.path.exists(path) if path else False
            report["blobs_check"].append({
                "path": path,
                "exists": exists,
                "ref": ref
            })
            if not exists:
                report["summary"]["missing_blobs"] = report["summary"].get("missing_blobs", 0) + 1

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Report generated: {args.output}")
    print(f"Total calls: {report['summary']['total_calls']}, Success Rate: {report['summary']['success_rate']:.2%}")

if __name__ == "__main__":
    main()
