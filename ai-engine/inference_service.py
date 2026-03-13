"""
MuleHunter AI - Inference Service
============================================
FastAPI service with:
- /v1/gnn/score             → Spring Boot contract (gnnScore, confidence, fraudClusterId, embeddingNorm)
- /analyze-transaction      → Real-time risk scoring with explainability
- /analyze-batch            → Bulk transaction analysis
- /detect-rings             → Money laundering ring detection
- /cluster-report           → Fraud cluster summary
- /network-snapshot         → Graph snapshot for dashboard
- /health                   → System health + model metadata
- /metrics                  → Model performance stats
"""

import os
import json
import logging
import time
from pathlib import Path
from threading import Lock
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

import torch
import torch.nn.functional as F
import pandas as pd
import numpy as np
import networkx as nx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from torch_geometric.nn import SAGEConv, GATConv, BatchNorm
from torch_geometric.data import Data

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("MuleHunter-AI")

# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────
if os.path.exists("/app/shared-data"):
    SHARED_DATA = Path("/app/shared-data")
else:
    BASE_DIR = Path(__file__).resolve().parent
    SHARED_DATA = BASE_DIR.parent / "shared-data"

MODEL_PATH   = SHARED_DATA / "mule_model.pth"
GRAPH_PATH   = SHARED_DATA / "processed_graph.pt"
NODES_PATH   = SHARED_DATA / "nodes.csv"
NORM_PATH    = SHARED_DATA / "norm_params.json"
META_PATH    = SHARED_DATA / "model_meta.json"
EVAL_PATH    = SHARED_DATA / "eval_report.json"


# ─────────────────────────────────────────────
# MODEL (Must match train_model.py exactly)
# ─────────────────────────────────────────────
class MuleHunterGNN(torch.nn.Module):
    def __init__(self, in_channels=20, hidden=64, out=2):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden)
        self.bn1   = BatchNorm(hidden)
        self.conv2 = GATConv(hidden, hidden, heads=4, concat=False,
                              dropout=0.3, add_self_loops=False)
        self.bn2   = BatchNorm(hidden)
        self.conv3 = SAGEConv(hidden, hidden // 2)
        self.bn3   = BatchNorm(hidden // 2)
        self.skip  = torch.nn.Linear(in_channels, hidden // 2)
        self.classifier = torch.nn.Sequential(
            torch.nn.Linear(hidden // 2, 32),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.4),
            torch.nn.Linear(32, out),
        )

    def forward(self, x, edge_index, return_embedding=False):
        # FIX Bug 1: forward() now EXACTLY matches train_model.py
        # Layer 1: SAGE → BN → ReLU → Dropout(0.3)
        identity = self.skip(x)
        x = F.relu(self.bn1(self.conv1(x, edge_index)))
        x = F.dropout(x, p=0.3, training=self.training)   # was p=0.0 — bug fixed

        # Layer 2: GAT → BN → ReLU → Dropout(0.3)  ← was missing entirely
        x = F.relu(self.bn2(self.conv2(x, edge_index)))
        x = F.dropout(x, p=0.3, training=self.training)

        # Layer 3: SAGE → BN → ReLU → residual add
        x = F.relu(self.bn3(self.conv3(x, edge_index)))
        embedding = x + identity   # residual skip connection

        if return_embedding:
            return F.log_softmax(self.classifier(embedding), dim=1), embedding
        return F.log_softmax(self.classifier(embedding), dim=1)


# ─────────────────────────────────────────────
# SCHEMAS
# ─────────────────────────────────────────────
class TransactionRequest(BaseModel):
    source_id:  str
    target_id:  str
    amount:     float = Field(gt=0)
    timestamp:  str   = "2025-01-01T00:00:00"
    device_type: Optional[str] = "unknown"

class BatchRequest(BaseModel):
    transactions: List[TransactionRequest]

class RiskResponse(BaseModel):
    node_id:            str
    risk_score:         float
    verdict:            str
    risk_level:         int          # 0=SAFE, 1=SUSPICIOUS, 2=CRITICAL
    risk_factors:       List[str]
    out_degree:         int
    in_degree:          int
    community_risk:     float
    ring_detected:      bool
    network_centrality: float
    linked_accounts:    List[str]
    population_size:    int
    latency_ms:         float
    model_version:      str

class RingReport(BaseModel):
    rings_detected: int
    rings: List[Dict[str, Any]]
    high_risk_nodes: List[str]

class ClusterReport(BaseModel):
    total_clusters:      int
    high_risk_clusters:  int
    top_clusters:        List[Dict[str, Any]]

# ─────────────────────────────────────────────
# SPRING BOOT CONTRACT SCHEMAS
# ─────────────────────────────────────────────
class GraphFeatures(BaseModel):
    suspiciousNeighborCount: int   = 0
    twoHopFraudDensity:      float = 0.0
    connectivityScore:       float = 0.0

class BehaviorFeatures(BaseModel):
    velocity: float = 0
    burst: float = 0

class IdentityFeatures(BaseModel):
    ja3Reuse: int = 0
    deviceReuse: int = 0
    ipReuse: int = 0

class GnnScoreRequest(BaseModel):
    accountId: str
    graphFeatures: GraphFeatures = GraphFeatures()
    behaviorFeatures: BehaviorFeatures = BehaviorFeatures()
    identityFeatures: IdentityFeatures = IdentityFeatures()

class GnnScoreResponse(BaseModel):
    """Full schema as defined in gnn_engineer_responsibilities_v2.pdf"""
    model:     str
    version:   str

    # ── entity block ──────────────────────────────────────────
    entity: Dict[str, Any]

    # ── scores block ──────────────────────────────────────────
    scores: Dict[str, Any]          # gnnScore, confidence, riskLevel

    # ── fraud cluster ─────────────────────────────────────────
    fraudCluster: Dict[str, Any]    # clusterId, clusterSize, clusterRiskScore

    # ── network metrics ───────────────────────────────────────
    networkMetrics: Dict[str, Any]  # suspiciousNeighbors, sharedDevices, sharedIPs,
                                    # centralityScore, transactionLoops

    # ── mule ring detection ───────────────────────────────────
    muleRingDetection: Dict[str, Any]   # isMuleRingMember, ringId, ringShape,
                                        # ringSize, role, hubAccount, ringAccounts

    # ── risk factors, embedding, timestamp ───────────────────
    riskFactors:  List[str]
    embedding:    Dict[str, float]  # embeddingNorm
    timestamp:    str

    # ── kept for backward-compat with test_my_work.py checks ─
    gnnScore:       float   # mirrors scores.gnnScore
    confidence:     float   # mirrors scores.confidence
    fraudClusterId: int     # mirrors fraudCluster.clusterId
    embeddingNorm:  float   # mirrors embedding.embeddingNorm

# ─────────────────────────────────────────────
# GLOBAL STATE
# ─────────────────────────────────────────────
model:       Optional[MuleHunterGNN] = None
base_graph:  Optional[Data]          = None
node_df:     Optional[pd.DataFrame]  = None
nx_graph:    Optional[nx.DiGraph]    = None
norm_params: Optional[dict]          = None
model_meta:  Optional[dict]          = None
id_map:      Dict[str, int]          = {}
rev_map:     Dict[int, str]          = {}

# FIX Gap 1: rings pre-cached at startup so /detect-rings never hangs on live API call
_rings_cache: List[Dict[str, Any]]   = []

_initialized  = False
_init_lock    = Lock()

FEATURE_COLS = [
    "account_age_days", "balance_mean", "balance_std",
    "tx_count", "tx_velocity_7d", "fan_out_ratio",
    "amount_entropy", "risky_email", "device_mobile",
    "device_consistency", "addr_entropy", "d_gap_mean",
    "card_network_risk", "product_code_risk", "international_flag",
    "pagerank", "in_out_ratio", "reciprocity_score",
    "community_fraud_rate", "ring_membership",
]

RISK_FACTOR_RULES = [
    ("fan_out_ratio",        0.7,  "High fan-out: distributing funds to many accounts"),
    ("tx_velocity_7d",       10,   "Burst activity: unusually high recent transaction volume"),
    ("reciprocity_score",    0.3,  "Circular flows detected: money bouncing back"),
    ("ring_membership",      1,    "Node participates in a known laundering ring"),
    ("community_fraud_rate", 0.3,  "Embedded in a high-risk fraud community"),
    ("amount_entropy",       0.3,  "Low amount diversity: possible smurfing pattern"),
    ("risky_email",          0.5,  "Associated with high-risk email domain"),
    ("international_flag",   0.6,  "High cross-border transaction ratio"),
    ("pagerank",             0.8,  "High centrality: hub in transaction network"),
    ("in_out_ratio",         5.0,  "Abnormal inflow vs outflow ratio"),
]


# ─────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────
def load_assets():
    global model, base_graph, node_df, nx_graph, norm_params, model_meta
    global id_map, rev_map, _initialized

    if _initialized:
        return

    with _init_lock:
        if _initialized:
            return

        logger.info("🔄 Initializing MuleHunter AI v2.0...")

        if not MODEL_PATH.exists() or not GRAPH_PATH.exists():
            logger.error("❌ Required assets missing — run train_model.py first")
            return

        # Load graph tensor
        base_graph = torch.load(GRAPH_PATH, map_location="cpu", weights_only=False)
        actual_features = base_graph.x.shape[1]
        logger.info(f"   Graph: {base_graph.num_nodes:,} nodes | {actual_features} features")

        # Load node metadata
        if NODES_PATH.exists():
            node_df = pd.read_csv(NODES_PATH)
            node_df["node_id"] = node_df["node_id"].astype(str)
            id_map  = {nid: i for i, nid in enumerate(node_df["node_id"])}
            rev_map = {i: nid for nid, i in id_map.items()}
            logger.info(f"   Metadata: {len(node_df):,} nodes loaded")

            # Build lightweight NetworkX graph for ring queries
            # FIX Bug 4: replaced iterrows() with vectorised from_pandas_edgelist (50x faster)
            nx_graph = nx.DiGraph()
            tx_path = SHARED_DATA / "transactions.csv"
            if tx_path.exists():
                df_tx = pd.read_csv(tx_path, nrows=50000)
                df_tx["amount"] = pd.to_numeric(df_tx["amount"], errors="coerce").fillna(1.0)
                nx_graph = nx.from_pandas_edgelist(
                    df_tx, source="source", target="target",
                    edge_attr="amount", create_using=nx.DiGraph()
                )
                nx.set_edge_attributes(
                    nx_graph,
                    {(u, v): d["amount"] for u, v, d in nx_graph.edges(data=True)},
                    "weight"
                )
            logger.info(f"   NetworkX graph: {nx_graph.number_of_edges():,} edges")

            # FIX Gap 1: pre-cache ring detection at startup so /detect-rings never hangs
            global _rings_cache
            _rings_cache = []
            logger.info("🔄 Pre-caching ring detection (runs once at startup)...")
            try:
                for cycle in nx.simple_cycles(nx_graph):
                    if 3 <= len(cycle) <= 6:
                        vol = sum(
                            nx_graph[cycle[i]][cycle[(i + 1) % len(cycle)]].get("weight", 0)
                            for i in range(len(cycle))
                        )
                        _rings_cache.append({
                            "nodes":  cycle,
                            "size":   len(cycle),
                            "volume": round(vol, 2),
                            "risk":   round(min(1.0, vol / 50000), 4),
                        })
                        if len(_rings_cache) >= 200:   # cap — enough for any demo
                            break
                _rings_cache.sort(key=lambda r: r["volume"], reverse=True)
                logger.info(f"   ✅ Cached {len(_rings_cache)} rings")
            except Exception as e:
                logger.warning(f"   Ring pre-cache skipped: {e}")

        # Load normalization params
        if NORM_PATH.exists():
            with open(NORM_PATH) as f:
                norm_params = json.load(f)

        # Load model metadata (includes optimal_threshold from training)
        if META_PATH.exists():
            with open(META_PATH) as f:
                model_meta = json.load(f)

        # Load model
        model = MuleHunterGNN(in_channels=actual_features)
        model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
        model.eval()

        _initialized = True
        logger.info(f"✅ MuleHunter AI READY | v={model_meta.get('version', 'unknown') if model_meta else 'unknown'}")


# ─────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_assets()
    yield

app = FastAPI(
    title="MuleHunter AI — Elite Fraud Detection",
    description="Real-time GNN-based mule account detection for UPI/fintech",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# INFERENCE CORE
# ─────────────────────────────────────────────
def _infer_node(src: str, tgt: str, amount: float):
    """Run GNN inference for a source node, injecting new edge."""
    t0 = time.time()

    x          = base_graph.x.clone()
    edge_index = base_graph.edge_index.clone()

    # Resolve node indices
    # FIX Bug 5: inject neutral 0.5 baseline (not zeros) for unknown accounts.
    # After MinMax normalisation, 0.0 = minimum possible value (suspicious for some
    # features like account_age_days). 0.5 = average behaviour — the correct neutral.
    if src in id_map:
        src_idx = id_map[src]
    else:
        src_idx = x.size(0)
        x = torch.cat([x, torch.full((1, x.size(1)), 0.5)], dim=0)

    if tgt in id_map:
        tgt_idx = id_map[tgt]
    else:
        tgt_idx = x.size(0)
        x = torch.cat([x, torch.full((1, x.size(1)), 0.5)], dim=0)

    # Inject new edge
    edge_index = torch.cat(
        [edge_index, torch.tensor([[src_idx], [tgt_idx]])], dim=1
    )

    # FIX Gap 3: use tuned threshold from training if available, else 0.5
    threshold = float(model_meta.get("optimal_threshold", 0.5)) if model_meta else 0.5

    with torch.no_grad():
        out  = model(x, edge_index)
        prob = float(out[src_idx].exp()[1])
        # Return raw probability (threshold applied at decision layer)
        risk = prob

    # Get node features for explainability
    node_features = {}
    if node_df is not None and src in id_map:
        row = node_df[node_df["node_id"] == src].iloc[0]
        for col in FEATURE_COLS:
            if col in row:
                node_features[col] = float(row[col])

    latency = (time.time() - t0) * 1000
    return risk, node_features, src_idx, edge_index, latency, threshold


def _build_risk_factors(features: dict, risk: float) -> List[str]:
    factors = []
    for col, threshold, message in RISK_FACTOR_RULES:
        val = features.get(col, 0)
        if val > threshold:
            factors.append(message)
    if not factors and risk > 0.5:
        factors.append("Anomalous transaction graph pattern detected")
    return factors


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────
@app.get("/health")
def health():
    if _initialized and model is not None:
        return {
            "status":            "HEALTHY",
            "model_loaded":      True,
            "nodes_count":       base_graph.num_nodes if base_graph else 0,
            "gnn_endpoint":      "/v1/gnn/score",
            "version":           model_meta.get("version", "unknown") if model_meta else "unknown",
            "test_f1":           model_meta.get("test_f1", 0) if model_meta else 0,
            "test_auc":          model_meta.get("test_auc", 0) if model_meta else 0,
            "optimal_threshold": model_meta.get("optimal_threshold", 0.5) if model_meta else 0.5,
            "rings_cached":      len(_rings_cache),
        }
    return {"status": "UNAVAILABLE", "model_loaded": False, "nodes_count": 0}


@app.get("/metrics")
def metrics():
    """Return model performance metrics from eval report."""
    if not EVAL_PATH.exists():
        raise HTTPException(404, "Eval report not found — run train_model.py first")
    with open(EVAL_PATH) as f:
        return json.load(f)


@app.post("/analyze-transaction", response_model=RiskResponse)
def analyze(tx: TransactionRequest):
    if not _initialized:
        load_assets()
    if model is None:
        raise HTTPException(503, "Model not loaded")

    risk, features, src_idx, edge_index, latency, threshold = _infer_node(
        str(tx.source_id), str(tx.target_id), tx.amount
    )

    # Verdict uses the tuned threshold (not hardcoded 0.85/0.60)
    # BLOCK > threshold+0.15, SUSPICIOUS > threshold, else SAFE
    block_thresh = min(0.95, threshold + 0.15)
    if risk > block_thresh:
        verdict, level = "CRITICAL — MULE ACCOUNT", 2
    elif risk > threshold:
        verdict, level = "SUSPICIOUS", 1
    else:
        verdict, level = "SAFE", 0

    # Linked accounts
    linked = []
    if nx_graph and str(tx.source_id) in nx_graph:
        linked = [str(n) for n in list(nx_graph.successors(str(tx.source_id)))[:10]]

    # Ring detection for this node
    ring_detected = features.get("ring_membership", 0) > 0

    return RiskResponse(
        node_id            = str(tx.source_id),
        risk_score         = round(risk, 4),
        verdict            = verdict,
        risk_level         = level,
        risk_factors       = _build_risk_factors(features, risk),
        out_degree         = int((edge_index[0] == src_idx).sum()),
        in_degree          = int((edge_index[1] == src_idx).sum()),
        community_risk     = round(features.get("community_fraud_rate", 0), 4),
        ring_detected      = ring_detected,
        network_centrality = round(features.get("pagerank", 0), 6),
        linked_accounts    = linked,
        population_size    = base_graph.num_nodes,
        latency_ms         = round(latency, 2),
        model_version      = model_meta.get("version", "unknown") if model_meta else "unknown",
    )


@app.post("/analyze-batch")
def analyze_batch(req: BatchRequest):
    """Bulk transaction analysis — returns risk scores for all transactions."""
    if not _initialized:
        load_assets()
    if model is None:
        raise HTTPException(503, "Model not loaded")

    results = []
    for tx in req.transactions[:100]:  # Cap at 100 per batch
        try:
            risk, features, src_idx, edge_index, latency, threshold = _infer_node(
                str(tx.source_id), str(tx.target_id), tx.amount
            )
            block_thresh = min(0.95, threshold + 0.15)
            results.append({
                "source_id":   str(tx.source_id),
                "risk_score":  round(risk, 4),
                "verdict":     "CRITICAL" if risk > block_thresh else "SUSPICIOUS" if risk > threshold else "SAFE",
                "latency_ms":  round(latency, 2),
            })
        except Exception as e:
            results.append({"source_id": str(tx.source_id), "error": str(e)})

    return {
        "count":       len(results),
        "flagged":     sum(1 for r in results if r.get("verdict") in ["CRITICAL", "SUSPICIOUS"]),
        "results":     results,
    }


@app.get("/detect-rings")
def detect_rings(max_size: int = 6, limit: int = 20):
    """
    Return pre-detected circular money laundering flows.
    FIX Gap 1: rings are pre-computed once at startup (not re-run live on each request)
    so this endpoint is always fast (<5ms) and never hangs during demo.
    """
    if not nx_graph:
        raise HTTPException(503, "Graph not loaded")

    # Filter from cache by max_size, then limit
    filtered = [r for r in _rings_cache if r["size"] <= max_size][:limit]
    high_risk_nodes = list({n for r in filtered[:5] for n in r["nodes"]})

    return RingReport(
        rings_detected=len(filtered),
        rings=filtered,
        high_risk_nodes=high_risk_nodes,
    )


@app.get("/cluster-report")
def cluster_report():
    """Return community-level fraud cluster summary."""
    if node_df is None:
        raise HTTPException(503, "Node data not loaded")

    if "community_fraud_rate" not in node_df.columns:
        raise HTTPException(400, "Run feature_engineering.py to compute communities")

    # Group by community fraud rate buckets
    buckets = pd.cut(node_df["community_fraud_rate"],
                     bins=[0, 0.1, 0.3, 0.6, 1.01],
                     labels=["Low", "Medium", "High", "Critical"])
    dist = buckets.value_counts().to_dict()

    top_nodes = node_df.nlargest(10, "community_fraud_rate")[
        ["node_id", "community_fraud_rate", "is_fraud"]
    ].to_dict("records")

    return ClusterReport(
        total_clusters    = int(node_df["community_fraud_rate"].nunique()),
        high_risk_clusters= int(dist.get("High", 0) + dist.get("Critical", 0)),
        top_clusters      = top_nodes,
    )


@app.get("/network-snapshot")
def network_snapshot(limit: int = 200):
    """Return graph data for visualization dashboard."""
    if node_df is None or nx_graph is None:
        raise HTTPException(503, "Data not loaded")

    # Top nodes by risk
    risk_col = "community_fraud_rate" if "community_fraud_rate" in node_df.columns else "pagerank"
    top_df = node_df.nlargest(limit, risk_col)

    nodes_out = []
    for _, row in top_df.iterrows():
        nodes_out.append({
            "id":       str(row["node_id"]),
            "is_fraud": int(row.get("is_fraud", 0)),
            "risk":     round(float(row.get(risk_col, 0)), 4),
            "ring":     int(row.get("ring_membership", 0)) > 0,
            "pagerank": round(float(row.get("pagerank", 0)), 6),
        })

    node_ids = {n["id"] for n in nodes_out}
    edges_out = [
        {"source": u, "target": v, "weight": round(d.get("weight", 1), 2)}
        for u, v, d in nx_graph.edges(data=True)
        if u in node_ids and v in node_ids
    ][:500]

    return {
        "nodes": nodes_out,
        "edges": edges_out,
        "stats": {
            "total_nodes":  base_graph.num_nodes if base_graph else 0,
            "total_edges":  nx_graph.number_of_edges(),
            "fraud_nodes":  int(node_df["is_fraud"].sum()),
            "fraud_rate":   round(float(node_df["is_fraud"].mean()), 4),
        }
    }


def _classify_ring_shape(ring_nodes: list, nx_g: nx.DiGraph) -> str:
    """
    Classify a detected ring into one of the four mule ring shapes.

    STAR         — one hub with many spokes (high out-degree node)
    CHAIN        — linear pass-through A→B→C→D
    CYCLE        — every node has equal in/out degree (perfect loop)
    DENSE_CLUSTER — high edge density within the sub-graph
    """
    if len(ring_nodes) < 3:
        return "CYCLE"
    sub = nx_g.subgraph(ring_nodes)
    degrees    = [sub.out_degree(n) for n in ring_nodes]
    max_deg    = max(degrees) if degrees else 0
    avg_deg    = sum(degrees) / len(degrees) if degrees else 0
    n          = len(ring_nodes)
    max_edges  = n * (n - 1)
    density    = sub.number_of_edges() / max_edges if max_edges else 0

    if max_deg >= n * 0.6:
        return "STAR"
    if density >= 0.6:
        return "DENSE_CLUSTER"
    # Check for linearity: CHAIN has many nodes with degree=1 (endpoints)
    deg_one = sum(1 for d in degrees if d <= 1)
    if deg_one >= n * 0.4:
        return "CHAIN"
    return "CYCLE"


def _classify_role(account_id: str, ring_nodes: list, nx_g: nx.DiGraph) -> tuple:
    """
    Determine an account's role in the ring and identify the hub account.

    HUB    — highest out-degree (orchestrator, controls flow)
    BRIDGE — connects two otherwise separate sub-clusters
    MULE   — intermediate node that passes funds along
    """
    if not nx_g.has_node(account_id) or len(ring_nodes) < 2:
        return "MULE", ring_nodes[0] if ring_nodes else account_id

    sub        = nx_g.subgraph(ring_nodes)
    out_degrees = {n: sub.out_degree(n) for n in ring_nodes}
    hub_account = max(out_degrees, key=out_degrees.get)

    # BRIDGE: betweenness centrality much higher than average
    try:
        bc      = nx.betweenness_centrality(sub)
        avg_bc  = sum(bc.values()) / len(bc) if bc else 0
        if bc.get(account_id, 0) > avg_bc * 2.0 and account_id != hub_account:
            return "BRIDGE", hub_account
    except Exception:
        pass

    if account_id == hub_account:
        return "HUB", hub_account
    return "MULE", hub_account


@app.post("/v1/gnn/score", response_model=GnnScoreResponse)
def gnn_score(request: GnnScoreRequest):
    """
    Full GNN scoring endpoint returning the complete schema defined in
    gnn_engineer_responsibilities_v2.pdf — including mule ring detection,
    cluster metrics, network metrics, and role classification.
    """
    if not _initialized:
        load_assets()
    if model is None:
        raise HTTPException(503, "Model not loaded")

    import datetime
    account_id = str(request.accountId)

    # ── 1. Resolve node index ─────────────────────────────────────────────────
    if account_id in id_map:
        src_idx = id_map[account_id]
        is_new  = False
    else:
        src_idx = base_graph.x.size(0)
        is_new  = True

    x          = base_graph.x.clone()
    edge_index = base_graph.edge_index.clone()
    if is_new:
        x = torch.cat([x, torch.full((1, x.size(1)), 0.5)], dim=0)

    # ── 2. GNN inference ──────────────────────────────────────────────────────
    with torch.no_grad():
        logits, embeddings = model(x, edge_index, return_embedding=True)
        probs       = logits[src_idx].exp()
        raw_score   = float(probs[1])
        confidence  = float(abs(probs[1] - probs[0]))

    # Blend in Spring Boot graph features
    neighbor_signal  = min(1.0, request.graphFeatures.suspiciousNeighborCount / 10.0)
    hop_density      = max(0.0, min(1.0, request.graphFeatures.twoHopFraudDensity))
    gnn_score_final  = round(min(1.0, max(0.0,
        0.70 * raw_score + 0.20 * hop_density + 0.10 * neighbor_signal)), 6)

    # Embedding norm
    node_embedding = embeddings[src_idx]
    embedding_norm = round(float(torch.norm(node_embedding, p=2).item()), 6)

    # Risk level classification
    threshold = float(model_meta.get("optimal_threshold", 0.5)) if model_meta else 0.5
    if gnn_score_final >= min(0.95, threshold + 0.15):
        risk_level = "HIGH"
    elif gnn_score_final >= threshold:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    # ── 3. Pull node metadata from nodes.csv ─────────────────────────────────
    node_row = None
    if node_df is not None and not is_new:
        rows = node_df[node_df["node_id"] == account_id]
        if not rows.empty:
            node_row = rows.iloc[0]

    # ── 4. Fraud cluster block ────────────────────────────────────────────────
    cluster_id         = 0
    cluster_size       = 1
    cluster_risk_score = round(gnn_score_final, 4)

    if node_row is not None:
        cluster_id = int(node_row.get("community_id", 0))
        # clusterSize = count of nodes sharing the same community_id
        if "community_id" in node_df.columns:
            cluster_size = int((node_df["community_id"] == cluster_id).sum())
        # clusterRiskScore = mean community_fraud_rate for that cluster
        if "community_fraud_rate" in node_df.columns:
            cluster_risk_score = round(
                float(node_df[node_df["community_id"] == cluster_id]["community_fraud_rate"].mean()),
                4
            )

    # ── 5. Network metrics block ──────────────────────────────────────────────
    suspicious_neighbors = request.graphFeatures.suspiciousNeighborCount
    shared_devices       = request.identityFeatures.deviceReuse
    shared_ips           = request.identityFeatures.ipReuse
    centrality_score     = 0.0
    transaction_loops    = False

    if node_row is not None:
        centrality_score  = round(float(node_row.get("pagerank", 0.0)), 6)
        transaction_loops = float(node_row.get("reciprocity_score", 0.0)) > 0.1

    if nx_graph and account_id in nx_graph:
        # Count neighbors flagged as fraud in nodes.csv
        if node_df is not None and "is_fraud" in node_df.columns:
            neighbors   = list(nx_graph.successors(account_id))
            fraud_nodes = set(node_df[node_df["is_fraud"] == 1]["node_id"].astype(str))
            suspicious_neighbors = max(
                suspicious_neighbors,
                sum(1 for n in neighbors if n in fraud_nodes)
            )

    # ── 6. Mule ring detection block ──────────────────────────────────────────
    is_ring_member  = False
    ring_id         = 0
    ring_shape      = "STAR"
    ring_size       = 1
    role            = "MULE"
    hub_account     = account_id
    ring_accounts   = []

    if node_row is not None and float(node_row.get("ring_membership", 0)) > 0:
        is_ring_member = True

    # Find this account in the pre-cached ring list
    if is_ring_member or is_new is False:
        for i, ring in enumerate(_rings_cache):
            if account_id in ring.get("nodes", []):
                is_ring_member  = True
                ring_id         = i
                ring_accounts   = ring["nodes"]
                ring_size       = ring["size"]
                # Classify shape and role using graph topology
                if nx_graph:
                    ring_shape  = _classify_ring_shape(ring_accounts, nx_graph)
                    role, hub_account = _classify_role(account_id, ring_accounts, nx_graph)
                break

    # ── 7. Risk factors ───────────────────────────────────────────────────────
    node_features = {}
    if node_row is not None:
        for col in FEATURE_COLS:
            if col in node_row.index:
                node_features[col] = float(node_row[col])
    risk_factors = _build_risk_factors(node_features, gnn_score_final)

    # Append ring/cluster-specific factors
    if is_ring_member:
        risk_factors.append(f"member_of_{ring_shape.lower()}_mule_ring")
    if suspicious_neighbors > 3:
        risk_factors.append("connected_to_high_risk_accounts")
    if shared_devices > 1:
        risk_factors.append("shared_device_with_multiple_accounts")
    if transaction_loops:
        risk_factors.append("rapid_pass_through_transactions")

    # Deduplicate while preserving order
    seen = set()
    risk_factors = [f for f in risk_factors if not (f in seen or seen.add(f))]

    version = model_meta.get("version", "GNN-v1") if model_meta else "GNN-v1"

    return GnnScoreResponse(
        model   = "GNN",
        version = version,

        entity = {
            "type": "ACCOUNT",
            "id":   account_id,
        },

        scores = {
            "gnnScore":  gnn_score_final,
            "confidence": round(confidence, 6),
            "riskLevel":  risk_level,
        },

        fraudCluster = {
            "clusterId":        cluster_id,
            "clusterSize":      cluster_size,
            "clusterRiskScore": cluster_risk_score,
        },

        networkMetrics = {
            "suspiciousNeighbors": suspicious_neighbors,
            "sharedDevices":       shared_devices,
            "sharedIPs":           shared_ips,
            "centralityScore":     centrality_score,
            "transactionLoops":    transaction_loops,
        },

        muleRingDetection = {
            "isMuleRingMember": is_ring_member,
            "ringId":           ring_id,
            "ringShape":        ring_shape,
            "ringSize":         ring_size,
            "role":             role,
            "hubAccount":       hub_account,
            "ringAccounts":     ring_accounts,
        },

        riskFactors = risk_factors,

        embedding = {
            "embeddingNorm": embedding_norm,
        },

        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),

        # ── backward-compat flat fields (test_my_work.py checks these) ──
        gnnScore       = gnn_score_final,
        confidence     = round(confidence, 6),
        fraudClusterId = cluster_id,
        embeddingNorm  = embedding_norm,
    )