import pandas as pd
import shap
from sklearn.ensemble import RandomForestClassifier
from typing import List, Dict

FEATURE_COLS = [
    "in_degree",
    "out_degree",
    "total_incoming",
    "total_outgoing",
    "risk_ratio",
    "tx_velocity",
    "account_age_days",
    "balance",
]

TOP_K = 3
MIN_SAMPLES = 20


def run_shap(scored_nodes: List[Dict]) -> List[Dict]:
    """
    Explain ONE anomalous target node using population-based SHAP.
    LAST row must be the target node.
    """

    if not scored_nodes or len(scored_nodes) < MIN_SAMPLES:
        return []

    df = pd.DataFrame(scored_nodes)

    required_cols = FEATURE_COLS + ["node_id", "is_anomalous", "anomaly_score"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for SHAP: {missing}")

    X = df[FEATURE_COLS].fillna(0)
    y = df["is_anomalous"]

    # MUST have at least 1 normal + 1 anomalous
    if y.nunique() < 2:
        return []

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=6,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1,
    )
    model.fit(X, y)

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)

    if isinstance(shap_values, list):
        shap_anomaly = shap_values[1]
    elif shap_values.ndim == 3:
        shap_anomaly = shap_values[:, :, 1]
    else:
        shap_anomaly = shap_values

    # 🔥 EXPLAIN TARGET NODE ONLY (LAST ROW)
    target_idx = len(df) - 1
    row = df.iloc[target_idx]
    impacts = shap_anomaly[target_idx]

    top_features = sorted(
        zip(FEATURE_COLS, impacts),
        key=lambda x: abs(x[1]),
        reverse=True
    )[:TOP_K]

    return [{
        "node_id": int(row["node_id"]),
        "anomaly_score": round(float(row["anomaly_score"]), 6),
        "top_factors": [
            {"feature": f, "impact": round(float(i), 6)}
            for f, i in top_features
        ],
        "model": "rf_surrogate",
        "source": "shap",
    }]
