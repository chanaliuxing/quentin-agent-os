import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quentin.memory.knowledge_graph import SimpleKnowledgeGraph

def test_kg():
    print("Testing KnowledgeGraph...")
    kg = SimpleKnowledgeGraph(repo_root=".")
    if kg.storage_path.exists(): kg.storage_path.unlink()
    
    kg.add_triple("A", "rel", "B")
    kg.add_triple("C", "rel", "A")
    
    res = kg.query("A")
    if len(res) != 2: raise ValueError("Query failed")
    
    txt = kg.get_context_text(["A"])
    if "rel" not in txt: raise ValueError("Context failed")
    
    print("KnowledgeGraph: OK")

if __name__ == "__main__":
    test_kg()
