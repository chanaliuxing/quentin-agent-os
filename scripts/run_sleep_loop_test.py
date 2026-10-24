import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import os
from quentin.memory.fabric import MemoryFabric
import asyncio
from quentin.sleep.loop import SleepLoop, SleepLoopConfig
from quentin.memory.models import MemoryRecord, MemoryTier, MemoryQuery

async def main():
    # Configure environment variables for embedding (assuming bge-m3 with 1024 dim)
    os.environ["MEM_EMBED_PROVIDER"] = "ollama"
    os.environ["MEM_EMBED_MODEL"] = "bge-m3"
    os.environ["MEM_EMBED_DIM"] = "1024"
    os.environ["LLM_BASE_URL"] = "http://localhost:11434"

    # You might need to set PG_HOST, PG_DSN if you want to use Postgres
    # For now, it will fall back to SQLite if PG_HOST/PG_DSN are not set.

    print("Initializing MemoryFabric...")
    fabric = MemoryFabric()

    print("Adding some test memories...")
    # Add some memories that should ideally cluster together
    await asyncio.to_thread(fabric.remember_atomic, "I learned how to use ollama to generate embeddings.", source="test_script")
    await asyncio.to_thread(fabric.remember_atomic, "Ollama is useful for local LLM and embedding models.", source="test_script")
    await asyncio.to_thread(fabric.remember_atomic, "The bge-m3 model provides 1024-dimensional embeddings.", source="test_script")
    await asyncio.to_thread(fabric.remember_atomic, "It's important to set MEM_EMBED_DIM correctly.", source="test_script")
    await asyncio.to_thread(fabric.remember_atomic, "This is an unrelated memory about cats.", source="test_script")
    
    # Wait a bit for memories to "age" for the sleep loop config (sts_min_age_hours)
    print("Waiting for memories to age (1 second for demonstration)...")
    await asyncio.sleep(1) # In a real scenario, this would be a longer duration or not needed for aged memories

    print("Initializing SleepLoop...")
    # Use a low age for testing purposes (e.g., 0 hours)
    config = SleepLoopConfig(sts_min_age_hours=0.0) 
    sleep_loop = SleepLoop(memory_fabric=fabric, config=config)

    print("Running SleepLoop once...")
    result = await sleep_loop.run_once()

    print("\nSleepLoop Result:")
    print(result.to_dict())

    # Verify if new MTS records were created
    print("\nChecking for new MTS records...")
    mts_records = fabric.recall(MemoryQuery(tier=MemoryTier.MTS, top_k=10))
    if mts_records:
        for i, rec in enumerate(mts_records):
            print(f"MTS Record {i+1}: ID={rec.id}, Content='{rec.content[:100]}...', Relations={rec.relations}")
    else:
        print("No MTS records found.")
        
    print("\nChecking for STS records (should be decayed)...")
    sts_records_after = fabric.recall(MemoryQuery(tier=MemoryTier.STS, top_k=10))
    if not sts_records_after:
        print("No STS records found (all decayed as expected).")
    else:
        print("Remaining STS records (unexpected):")
        for i, rec in enumerate(sts_records_after):
            print(f"STS Record {i+1}: ID={rec.id}, Content='{rec.content[:100]}...'")

if __name__ == "__main__":
    asyncio.run(main())
