import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

# 1. Mock git.Repo
try:
    import git
    git.Repo = MagicMock()
except ImportError:
    pass

# 2. Setup imports
sys.path.insert(0, str(Path(__file__).parent))

from app.main import run_temporal
from app.config import settings
from app.observability.logger import setup_logging
from app.observability.tracer import setup_tracing

async def start():
    if len(sys.argv) < 2:
        print("Usage: python run.py <prd_file.md> [project_id]")
        return

    prd_path = sys.argv[1]
    project_id = sys.argv[2] if len(sys.argv) > 2 else "snake-game"

    settings.ensure_dirs()
    setup_logging()
    setup_tracing()
    
    print(f"🚀 Starting AutoLoop Task: {prd_path}")
    
    try:
        await run_temporal(project_id, prd_path)
        print("\n✅ Task completed successfully!")
    except Exception as e:
        print(f"\n❌ Task failed: {e}")

if __name__ == "__main__":
    asyncio.run(start())
