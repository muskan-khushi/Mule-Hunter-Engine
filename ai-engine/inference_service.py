import os
import logging
import torch
import torch.nn.functional as F
import pandas as pd
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel, Field
from torch_geometric.nn import SAGEConv
from torch_geometric.data import Data
from threading import Lock

# =================================================
# LOGGING
# =================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MuleHunter-Inference")

# =================================================
# PATHS (Docker-safe)
# =================================================
SHARED_DATA = "/app/shared-data"

MODEL_PATH = f"{SHARED_DATA}/mule_model.pth"
GRAPH_PATH = f"{SHARED_DATA}/processed_graph.pt"
NODES_PATH = f"{SHARED_DATA}/nodes.csv"

# =================================================
# MODEL
# =================================================
class MuleSAGE(torch.nn.Module):
    def __init__(self, in_channels=5, hidden_channels=32, out_channels=2):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, out_channels)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = self.conv2(x, edge_index)
        return F.log_softmax(x, dim=1)

# =================================================
# API SCHEMAS
# =================================================
class TransactionRequest(BaseModel):
    source_id: int
    target_id: int
    amount: float = Field(gt=0)
    timestamp: str = "2025-12-25"

class RiskResponse(BaseModel):
    node_id: int
    risk_score: float
    verdict: str
    out_degree: int
    linked_accounts: List[str]
    population_size: int
    model_version: str

# =================================================
# GLOBAL STATE
# =================================================
model: Optional[MuleSAGE] = None
base_graph: Optional[Data] = None

node_df: Optional[pd.DataFrame] = None
id_map: dict = {}
rev_map: dict = {}

_initialized = False
_init_lock = Lock()

# =================================================
# LOAD ASSETS (SAFE + OPTIONAL CSV)
# =================================================
def load_assets():
    global model, base_graph, node_df, id_map, rev_map, _initialized

    if _initialized:
        return

    with _init_lock:
        if _initialized:
            return

        logger.info("🔄 Initializing MuleHunter AI...")

        # ---- REQUIRED ASSETS
        if not all(os.path.exists(p) for p in [MODEL_PATH, GRAPH_PATH]):
            raise RuntimeError("❌ Missing required model or graph assets")

        # ---- LOAD GRAPH
        base_graph = torch.load(
            GRAPH_PATH,
            map_location="cpu",
            weights_only=False
        )

        # ---- OPTIONAL nodes.csv
        if os.path.exists(NODES_PATH):
            try:
                node_df = pd.read_csv(NODES_PATH)
                node_df["node_id"] = node_df["node_id"].astype(str)

                id_map = {nid: i for i, nid in enumerate(node_df["node_id"])}
                rev_map = {i: nid for nid, i in id_map.items()}

                logger.info(f"ℹ️ nodes.csv loaded ({len(node_df)} rows)")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load nodes.csv: {e}")
                node_df = None
        else:
            logger.info("ℹ️ nodes.csv not found — running in graph-only mode")

        # ---- LOAD MODEL
        model = MuleSAGE()
        model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
        model.eval()

        _initialized = True
        logger.info(f"✅ AI READY | Graph Nodes: {base_graph.num_nodes}")

# =================================================
# FASTAPI APP
# =================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        load_assets()
    except Exception as e:
        logger.warning(f"Startup init failed (will retry on request): {e}")
    yield

app = FastAPI(
    title="Mule Hunter AI – Production Inference",
    lifespan=lifespan
)

# =================================================
# INFERENCE ENDPOINT
# =================================================
@app.post("/analyze-transaction", response_model=RiskResponse)
def analyze_transaction(tx: TransactionRequest):

    if not _initialized:
        load_assets()

    # ---- CLONE GRAPH (SAFE)
    x = base_graph.x.clone()
    edge_index = base_graph.edge_index.clone()

    # ---- SOURCE NODE
    src_key = str(tx.source_id)

    if node_df is not None and src_key in id_map:
        src_idx = id_map[src_key]
        row = node_df.iloc[src_idx]

        features = torch.tensor([
            row.account_age_days,
            tx.amount / 1000.0,
            row.in_out_ratio,
            row.pagerank,
            row.tx_velocity + 1
        ], dtype=torch.float)

        x[src_idx] = features
    else:
        src_idx = x.size(0)
        features = torch.tensor([
            30.0,
            tx.amount / 1000.0,
            1.0,
            0.0001,
            1.0
        ], dtype=torch.float)

        x = torch.cat([x, features.unsqueeze(0)], dim=0)

    # ---- TARGET NODE
    tgt_key = str(tx.target_id)

    if node_df is not None and tgt_key in id_map:
        tgt_idx = id_map[tgt_key]
    else:
        tgt_idx = x.size(0)
        x = torch.cat([x, torch.zeros((1, x.size(1)))], dim=0)

    # ---- EDGE INJECTION
    new_edge = torch.tensor([[src_idx], [tgt_idx]], dtype=torch.long)
    edge_index = torch.cat([edge_index, new_edge], dim=1)

    # ---- INFERENCE
    with torch.no_grad():
        out = model(x, edge_index)
        risk = float(out[src_idx].exp()[1])

    # ---- DEGREE & NEIGHBORS
    mask = edge_index[0] == src_idx
    neighbors = edge_index[1][mask]

    linked = [
        f"Card_{rev_map.get(n.item(), 'NEW')}"
        for n in neighbors[:3]
    ]

    verdict = (
        "CRITICAL (MULE)" if risk > 0.85 else
        "SUSPICIOUS" if risk > 0.6 else
        "SAFE"
    )

    return {
        "node_id": tx.source_id,
        "risk_score": round(risk, 4),
        "verdict": verdict,
        "out_degree": int(mask.sum()),
        "linked_accounts": linked,
        "population_size": x.size(0),
        "model_version": "Kaggle-V4-Final-Inductive"
    }
