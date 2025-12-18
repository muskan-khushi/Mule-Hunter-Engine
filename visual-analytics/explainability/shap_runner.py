import pandas as pd
import numpy as np
import shap
import json
import os
from sklearn.ensemble import RandomForestClassifier

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "shared-data"))

INPUT_FILE = os.path.join(SHARED_DATA_DIR, "nodes_scored.csv")
OUTPUT_FILE = os.path.join(SHARED_DATA_DIR, "shap_explanations.json")

FEATURE_COLS = [
    "in_degree",
    "out_degree",
    "total_incoming",
    "total_outgoing",
    "risk_ratio",
    "tx_velocity",
    "account_age_days",
    "balance"
]

def run_shap_explainer():
    print(" Running SHAP Explainability Pipeline...")

    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        return

    df = pd.read_csv(INPUT_FILE)

    # Train surrogate model
    X = df[FEATURE_COLS].fillna(0)
    y = df["is_anomalous"]

    model = RandomForestClassifier(
        n_estimators=150,
        max_depth=6,
        random_state=42,
        class_weight="balanced"
    )
    model.fit(X, y)

    # --- SHAP Explainer Logic ---
    explainer = shap.TreeExplainer(model)
    raw_shap_values = explainer.shap_values(X)

    # Handle different SHAP output formats (List vs 3D Array)
    if isinstance(raw_shap_values, list):
        # Format: [array_class_0, array_class_1]
        shap_values_anomalous = raw_shap_values[1]
    elif len(raw_shap_values.shape) == 3:
        # Format: (samples, features, classes)
        shap_values_anomalous = raw_shap_values[:, :, 1]
    else:
        # Format: (samples, features) - already sliced or regression style
        shap_values_anomalous = raw_shap_values

    explanations = []

    # Get original positional indices of anomalous nodes
    anomalous_positions = df.index[df["is_anomalous"] == 1].tolist()

    for pos in anomalous_positions:
        # Get feature contributions for this specific anomalous row
        contribs = shap_values_anomalous[pos]
        
        feature_impacts = sorted(
            zip(FEATURE_COLS, contribs),
            key=lambda x: abs(x[1]),
            reverse=True
        )[:3]

        row = df.iloc[pos]  # Use positional indexing for safety
        explanations.append({
            "node_id": int(row["node_id"]),
            "anomaly_score": round(float(row["anomaly_score"]), 3),
            "top_factors": [
                {
                    "feature": f,
                    "impact": round(float(v), 3)
                } for f, v in feature_impacts
            ]
        })

    # Save results
    with open(OUTPUT_FILE, "w") as f:
        json.dump(explanations, f, indent=2)

    print(f" SHAP explanations saved → {OUTPUT_FILE}")
    print(f" Explained nodes: {len(explanations)}")

if __name__ == "__main__":
    run_shap_explainer()