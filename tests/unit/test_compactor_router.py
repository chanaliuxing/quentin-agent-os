import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.llm.compactors.router import compactor_router

def test_router():
    t = compactor_router.get_compactor("truncate")
    assert t.__class__.__name__ == "TruncateCompactor"
    
    s = compactor_router.get_compactor("summary")
    assert s.__class__.__name__ == "SummaryCompactor"
    
    d = compactor_router.get_compactor("unknown")
    assert d.__class__.__name__ == "TruncateCompactor"
    print("CompactorRouter: OK")

if __name__ == "__main__":
    test_router()
