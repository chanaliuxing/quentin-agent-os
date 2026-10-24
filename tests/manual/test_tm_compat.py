import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.tools.manager import ToolManager

def test_tm():
    tm = ToolManager()
    if hasattr(tm, "register"):
        print("✅ ToolManager.register exists.")
    else:
        print("❌ ToolManager.register MISSING.")
        exit(1)
        
    try:
        tm.register("ls", lambda x: "ok")
        print("✅ Register call succeeded.")
    except Exception as e:
        print(f"❌ Register call failed: {e}")
        exit(1)

if __name__ == "__main__":
    test_tm()
