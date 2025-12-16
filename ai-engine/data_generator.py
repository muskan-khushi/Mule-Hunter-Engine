import networkx as nx
import pandas as pd
import random
from faker import Faker
import numpy as np
import os

# --- CONFIGURATION ---
NUM_USERS = 2000
NUM_MULE_RINGS = 50
NUM_CHAINS = 50
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared-data")

# Setup
fake = Faker('en_IN')
Faker.seed(42)
np.random.seed(42)
random.seed(42)

def generate_dataset():
    print(f"🚀 Initializing Mule Hunter Simulation...")
    print(f"📂 Output Target: {OUTPUT_DIR}")
    
    # Ensure output directory exists
    if not os.path.exists(OUTPUT_DIR):
        print(f"⚠️  Folder {OUTPUT_DIR} not found. Creating it...")
        os.makedirs(OUTPUT_DIR)

    # --- STEP 1: Benign Economy ---
    print("   Building Scale-Free Network...")
    G = nx.barabasi_albert_graph(n=NUM_USERS, m=2, seed=42)
    
    for i in G.nodes():
        G.nodes[i]['is_fraud'] = 0
        G.nodes[i]['type'] = 'Legit'
        G.nodes[i]['account_age'] = random.randint(30, 3650)

    # --- STEP 2: Mule Rings (Star) ---
    print(f"💉 Injecting {NUM_MULE_RINGS} Mule Rings...")
    for _ in range(NUM_MULE_RINGS):
        mule = random.choice(list(G.nodes()))
        criminal = random.choice(list(G.nodes()))
        
        G.nodes[mule]['is_fraud'] = 1
        G.nodes[mule]['type'] = 'Mule'
        G.nodes[criminal]['is_fraud'] = 1
        G.nodes[criminal]['type'] = 'Criminal'
        
        # Fan-Out
        G.add_edge(mule, criminal, amount=random.randint(50000, 100000), timestamp=100)
        # Fan-In
        for _ in range(random.randint(10, 20)):
            victim = random.choice(list(G.nodes()))
            if G.nodes[victim]['is_fraud'] == 0:
                G.add_edge(victim, mule, amount=random.randint(500, 2000), timestamp=random.randint(1, 90))

    # --- STEP 3: Laundering Chains ---
    print(f"💉 Injecting {NUM_CHAINS} Chains...")
    for _ in range(NUM_CHAINS):
        chain = random.sample(list(G.nodes()), 5)
        for i in range(len(chain) - 1):
            src, dst = chain[i], chain[i+1]
            G.nodes[src]['is_fraud'] = 1
            G.nodes[dst]['is_fraud'] = 1
            G.nodes[src]['type'] = 'Layer'
            G.add_edge(src, dst, amount=50000 - (i*1000), timestamp=100+i)

   # --- STEP 4: Export ---
    print("💾 Saving Data...")
    
    # Nodes
    node_data = [{"node_id": n, "name": fake.name(), "is_fraud": G.nodes[n]['is_fraud'], "type": G.nodes[n]['type']} for n in G.nodes()]
    pd.DataFrame(node_data).to_csv(os.path.join(OUTPUT_DIR, "nodes.csv"), index=False)

    # Transactions (Edges)
    # FIX: Use .get() to provide default values for normal edges
    edge_data = []
    for u, v, d in G.edges(data=True):
        edge_data.append({
            "source": u,
            "target": v,
            "amount": d.get('amount', random.randint(100, 5000)),  # Default: Small normal transaction
            "timestamp": d.get('timestamp', random.randint(0, 1000)) # Default: Random time
        })
        
    pd.DataFrame(edge_data).to_csv(os.path.join(OUTPUT_DIR, "transactions.csv"), index=False)
    
    print(f"✅ SUCCESS! Data locked in shared-data.")

if __name__ == "__main__":
    generate_dataset()