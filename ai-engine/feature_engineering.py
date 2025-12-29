import pandas as pd
import networkx as nx
import torch
import os
import numpy as np
from torch_geometric.data import Data

SHARED_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared-data")

def build_graph_data():
    print("🚀 Starting Final Feature Engineering...")
    
    df_nodes = pd.read_csv(os.path.join(SHARED_DATA_DIR, "nodes.csv"))
    df_tx = pd.read_csv(os.path.join(SHARED_DATA_DIR, "transactions.csv"))

    # CRITICAL FIX: Ensure all IDs are strings so they match perfectly
    df_nodes['node_id'] = df_nodes['node_id'].astype(str)
    df_tx['source'] = df_tx['source'].astype(str)
    df_tx['target'] = df_tx['target'].astype(str)

    print("   🕸️ Building Graph (Card -> Address)...")
    G = nx.DiGraph()
    G.add_nodes_from(df_nodes['node_id'])
    
    # Add edges from Kaggle transactions
    edges = list(zip(df_tx['source'], df_tx['target'], df_tx['amount']))
    for src, tgt, amt in edges:
        G.add_edge(src, tgt, amount=amt)

    print("   📊 Calculating Kaggle Network Metrics...")
    pagerank_scores = nx.pagerank(G)

    # Calculate metrics for the 5-feature model
    metrics = []
    for node_id in df_nodes['node_id']:
        d_out = G.out_degree(node_id)
        
        # Money Flow
        out_amt = sum([d.get('amount', 0) for _, _, d in G.out_edges(node_id, data=True)])
        in_amt = sum([d.get('amount', 0) for _, _, d in G.in_edges(node_id, data=True)])
        
        ratio = in_amt / (out_amt + 1e-5)
        # Velocity is how many times this card appears in the transactions file
        velocity = len(df_tx[df_tx['source'] == node_id])
        
        metrics.append({
            'node_id': node_id,
            'out_degree': d_out,
            'risk_ratio': round(ratio, 4),
            'tx_velocity': velocity,
            'pagerank': pagerank_scores.get(node_id, 0)
        })

    # Update the nodes dataframe
    df_metrics = pd.DataFrame(metrics)
    df_nodes = df_nodes.drop(columns=['out_degree', 'risk_ratio', 'tx_velocity', 'pagerank', 'in_degree'], errors='ignore')
    df_nodes = pd.merge(df_nodes, df_metrics, on='node_id', how='left')

    # Keep schema names identical for Frontend safety
    df_nodes['in_out_ratio'] = df_nodes['risk_ratio']
    
    df_nodes.to_csv(os.path.join(SHARED_DATA_DIR, "nodes.csv"), index=False)
    print("   ✅ Updated nodes.csv with REAL Kaggle metrics.")

    # 💾 Save for AI Trainer
    node_mapping = {id: idx for idx, id in enumerate(df_nodes['node_id'])}
    src_idx = df_tx['source'].map(node_mapping)
    tgt_idx = df_tx['target'].map(node_mapping)
    
    valid_mask = src_idx.notna() & tgt_idx.notna()
    edge_index = torch.tensor([src_idx[valid_mask].values, tgt_idx[valid_mask].values], dtype=torch.long)
    
    # Normalize features for the Neural Network
    feature_cols = ["account_age_days", "balance", "in_out_ratio", "pagerank", "tx_velocity"]
    x = torch.tensor(df_nodes[feature_cols].values, dtype=torch.float)
    y = torch.tensor(df_nodes['is_fraud'].values, dtype=torch.long)

    data = Data(x=x, edge_index=edge_index, y=y)
    torch.save(data, os.path.join(SHARED_DATA_DIR, "processed_graph.pt"))
    print("✅ SUCCESS: Processed Graph Tensor saved.")

if __name__ == "__main__":
    build_graph_data()