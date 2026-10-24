from __future__ import annotations
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def sys_top_snapshot(params: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    P5: Ported from OpenClaw's system-monitor.
    Snapshots the top 5 CPU consuming processes.
    """
    try:
        import psutil
    except ImportError:
        return {
            "status": "error",
            "error": "feature_unavailable: psutil not installed",
            "hint": "Run 'pip install psutil' to enable system monitoring tools.",
            "result": "System monitoring is unavailable because 'psutil' is not installed."
        }

    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
            
    # Sort by CPU
    top_cpu = sorted(processes, key=lambda x: x.get('cpu_percent', 0), reverse=True)[:5]
    
    # Format for LLM
    lines = []
    for p in top_cpu:
        mem_info = p.get('memory_info')
        rss = mem_info.rss if mem_info else 0
        mem_mb = rss / (1024 * 1024)
        lines.append(f"PID: {p.get('pid')} | NAME: {p.get('name')} | CPU: {p.get('cpu_percent')}% | MEM: {mem_mb:.1f}MB")
        
    return {
        "status": "ok",
        "top_processes": top_cpu,
        "result": "System Resource Snapshot (Top CPU):\n" + "\n".join(lines)
    }
