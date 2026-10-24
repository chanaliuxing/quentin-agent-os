import os
import psycopg
from psycopg.rows import dict_row

def check():
    dsn = f"postgresql://{os.environ['PG_USER']}:{os.environ['PG_PASSWORD']}@{os.environ['PG_HOST']}:{os.environ['PG_PORT']}/{os.environ['PG_DB']}"
    print(f"Connecting to {dsn.split('@')[-1]}...")
    
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        print("\n--- 1. Check MTS Records ---")
        cur = conn.execute("SELECT id, content, tier FROM memories WHERE tier='mid_term' ORDER BY created_at DESC LIMIT 1;")
        row = cur.fetchone()
        if row:
            print("✅ Found MTS:", row)
        else:
            print("❌ No MTS found!")

        print("\n--- 2. Check Knowledge Graph Nodes (Memory) ---")
        cur = conn.execute("SELECT node_id, ref_id, title FROM kg_nodes WHERE node_type='memory' ORDER BY created_at DESC LIMIT 1;")
        row = cur.fetchone()
        if row:
            print("✅ Found KG Node:", row)
        else:
            print("❌ No Memory Node found in KG!")

        print("\n--- 3. Check Knowledge Graph Edges (crystallized_from) ---")
        cur = conn.execute("SELECT * FROM kg_edges WHERE edge_type='crystallized_from' ORDER BY created_at DESC LIMIT 1;")
        row = cur.fetchone()
        if row:
            print("✅ Found KG Edge:", row)
        else:
            print("❌ No 'crystallized_from' Edge found in KG!")

        print("\n--- 4. Check Skill Node (calc_fibonacci) ---")
        cur = conn.execute("SELECT node_id, ref_id, title FROM kg_nodes WHERE node_type='skill' AND ref_id='calc_fibonacci';")
        row = cur.fetchone()
        if row:
            print("✅ Found Skill Node:", row)
        else:
            print("❌ No Skill Node found for calc_fibonacci!")

        print("\n--- 5. Check Skill Provenance (Edges) ---")
        cur = conn.execute("""
            SELECT e.* 
            FROM kg_edges e 
            JOIN kg_nodes n ON e.dst_node_id = n.node_id 
            WHERE n.ref_id='calc_fibonacci'
        """)
        rows = cur.fetchall()
        if rows:
            print(f"✅ Found {len(rows)} Edges for Skill:", rows)
        else:
            print("❌ No Edges found for Skill!")

if __name__ == "__main__":
    check()
