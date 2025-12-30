import torch
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv
from torch_geometric.data import Data
import os
import pandas as pd
import numpy as np

# --- CONFIGURATION FIX ---
# os.getcwd() gets the directory where you ran the 'python' command.
# If you are in the project root, this will correctly find /shared-data
ROOT_DIR = os.getcwd() 
SHARED_DATA_DIR = os.path.join(ROOT_DIR, "shared-data")

# Ensure the paths are absolute and clean
NODES_PATH = os.path.normpath(os.path.join(SHARED_DATA_DIR, "nodes.csv"))
EDGES_PATH = os.path.normpath(os.path.join(SHARED_DATA_DIR, "transactions.csv"))
MODEL_SAVE_PATH = os.path.normpath(os.path.join(SHARED_DATA_DIR, "mule_model.pth"))
DATA_LOAD_PATH = os.path.normpath(os.path.join(SHARED_DATA_DIR, "processed_graph.pt"))

# Verify paths in console for debugging
print(f"🔍 Training script looking for data in: {SHARED_DATA_DIR}")

# --- DEFINING THE GNN (Must match inference_service.py exactly) ---
class MuleSAGE(torch.nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels):
        super(MuleSAGE, self).__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, out_channels)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = self.conv2(x, edge_index)
        return F.log_softmax(x, dim=1)

def train():
    print("🚀 Training AI on Kaggle IEEE-CIS Financial Network...")

    # 1. Load the Engineered Graph Data
    if not os.path.exists(DATA_LOAD_PATH):
        raise FileNotFoundError(f"❌ Graph data not found at {DATA_LOAD_PATH}. Check your root directory!")
    
    data = torch.load(DATA_LOAD_PATH, weights_only=False)

    # 2. Handle Class Imbalance
    fraud_count = int(data.y.sum())
    safe_count = len(data.y) - fraud_count
    
    # Weights optimized for IEEE-CIS (1:15 ratio)
    class_weights = torch.tensor([1.0, 15.0]).to(data.x.device)

    # 3. Initialize Model with 32 hidden channels for Kaggle
    model = MuleSAGE(in_channels=5, hidden_channels=32, out_channels=2)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.005, weight_decay=1e-4)

    # 4. Training Loop
    model.train()
    print(f"   Nodes: {data.x.size(0)} | Edges: {data.edge_index.size(1)} | Fraud Cases: {fraud_count}")

    for epoch in range(201):
        optimizer.zero_grad()
        out = model(data.x, data.edge_index)
        loss = F.nll_loss(out, data.y, weight=class_weights)
        loss.backward()
        optimizer.step()
        
        if epoch % 20 == 0:
            pred = out.argmax(dim=1)
            correct = (pred == data.y).sum().item()
            acc = correct / len(data.y)
            print(f"   Epoch {epoch:3d} | Loss: {loss.item():.4f} | Train Acc: {acc:.2%}")

    # 5. Save Model Weights
    torch.save(model.state_dict(), MODEL_SAVE_PATH)
    print(f"🎉 SUCCESS! Kaggle-trained model saved to {MODEL_SAVE_PATH}")

if __name__ == "__main__":
    train()