from typing import List, Dict, Tuple
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler



# CONFIG


FEATURE_COLS = [
    "in_degree",
    "out_degree",
    "total_incoming",
    "total_outgoing",
    "risk_ratio",
]

MIN_POPULATION_SIZE = 10



# TRAINING


def train_isolation_forest(
    reference_nodes: List[Dict],
) -> Tuple[IsolationForest, StandardScaler]:
    """
    Trains Isolation Forest on reference population.

    Args:
        reference_nodes → list of normalized nodes (snake_case)

    Returns:
        trained model + fitted scaler
    """

    if not reference_nodes or len(reference_nodes) < MIN_POPULATION_SIZE:
        raise ValueError("Insufficient population for Isolation Forest")

    df = pd.DataFrame(reference_nodes)

   
    # Feature preparation
    

    X = df[FEATURE_COLS].fillna(0)

    # Log-scale heavy-tailed features
    X = X.copy()
    X["total_incoming"] = np.log1p(X["total_incoming"])
    X["total_outgoing"] = np.log1p(X["total_outgoing"])
    X["risk_ratio"] = np.log1p(X["risk_ratio"])

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

   
    # Model
    

    model = IsolationForest(
        n_estimators=300,
        contamination=0.05,   # demo + small data friendly
        max_samples="auto",
        random_state=42,
        n_jobs=-1,
    )
    

    model.fit(X_scaled)

    return model, scaler



# SCORING


def score_nodes(
    model: IsolationForest,
    scaler: StandardScaler,
    nodes: List[Dict],
) -> List[Dict]:
    """
    Scores nodes using a trained Isolation Forest.

    Args:
        model  → trained IsolationForest
        scaler → fitted StandardScaler
        nodes  → list of normalized nodes (snake_case)

    Returns:
        List of anomaly score dicts
    """

    if not nodes:
        return []

    df = pd.DataFrame(nodes)

    X = df[FEATURE_COLS].fillna(0)

    
    X = X.copy()
    X["total_incoming"] = np.log1p(X["total_incoming"])
    X["total_outgoing"] = np.log1p(X["total_outgoing"])
    X["risk_ratio"] = np.log1p(X["risk_ratio"])

    X_scaled = scaler.transform(X)

    raw_scores = model.decision_function(X_scaled)
    anomaly_scores = -raw_scores
    preds = model.predict(X_scaled)

    results = []
    print("📉 Raw IF scores:", anomaly_scores[:5])
    print("📉 Predictions:", preds[:5])


    for i in range(len(df)):
        results.append({
            "node_id": int(df.iloc[i]["node_id"]),
            "anomaly_score": round(float(anomaly_scores[i]), 6),
            "is_anomalous": int(preds[i] == -1),
            "model": "isolation_forest",
            "source": "visual-analytics",
        })

    return results
