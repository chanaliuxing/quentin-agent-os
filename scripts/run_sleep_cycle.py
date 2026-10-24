import asyncio
from quentin.sleep.loop import SleepLoop, SleepLoopConfig
from quentin.memory.fabric import MemoryFabric
from quentin.traces.core import JsonlTraceRecorder
from quentin.orchestrator.ollama_council_preset import create_default_ollama_council

def main():
    """
    Manually trigger a sleep cycle.
    """
    memory_fabric = MemoryFabric(db_path="data/memory.db")
    trace_recorder = JsonlTraceRecorder(repo_root=".")
    council = create_default_ollama_council()

    sleep_loop = SleepLoop(
        config=SleepLoopConfig(),
        trace_recorder=trace_recorder,
        memory_fabric=memory_fabric,
        council=council,
    )

    print("Running sleep cycle...")
    report = asyncio.run(sleep_loop.run_once())
    print("Sleep cycle finished.")
    print(f"  STS processed: {report.processed_sts}")
    print(f"  MTS items created: {report.mts_created}")

if __name__ == "__main__":
    main()
