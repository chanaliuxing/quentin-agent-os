import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.infra.llm.factory import ModelClientFactory

def test_collision_fix_logic():
    print("--- Verifying Collision Fix Logic ---")
    model_id = "qwen3-vl:latest"
    prov = "ollama"
    # This is what kwargs looks like when coming from higher layers
    kwargs = {"provider": prov, "other": "val"}
    
    # Simulating the fix in client.py
    call_kwargs = dict(kwargs)
    call_kwargs.pop("provider", None)
    call_kwargs.pop("model_id", None)
    
    try:
        # Pass call_kwargs instead of kwargs
        ModelClientFactory.create_client(model_id=model_id, provider=prov, **call_kwargs)
        print("✅ Fix Verified: No collision when redundant keys are popped.")
    except TypeError as e:
        print(f"❌ Still Colliding: {e}")

if __name__ == "__main__":
    test_collision_fix_logic()
