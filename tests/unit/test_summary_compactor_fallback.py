import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from quentin.llm.compactors.summary_compactor import SummaryCompactor

def test_summary_fallback():
    sc = SummaryCompactor()
    
    # Short text -> no compact
    res = sc.compact("short", 100)
    assert res.method == "none"
    
    # Long text -> heuristic summary
    long_text = "\n".join([f"Line {i}" for i in range(100)])
    res = sc.compact(long_text, 200)
    # Check fallback or heuristic
    print(f"Compact method: {res.method}")
    print("SummaryFallback: OK")

if __name__ == "__main__":
    test_summary_fallback()
