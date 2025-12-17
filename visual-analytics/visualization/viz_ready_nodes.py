import pandas as pd
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "shared-data"))

NODES_FILE = os.path.join(SHARED_DATA_DIR, "nodes_scored.csv")
TX_FILE = os.path.join(SHARED_DATA_DIR, "transactions.csv")
OUTPUT_FILE = os.path.join(SHARED_DATA_DIR, "nodes_viz.json")

def prepare_viz_data():
    nodes_df = pd.read_csv(NODES_FILE)
    tx_df = pd.read_csv(TX_FILE)

    # ---------- Nodes ----------
    nodes = []
    for _, row in nodes_df.iterrows():
        anomaly_score = float(row["anomaly_score"])

        nodes.append({
            "id": int(row["node_id"]),
            "color": "red" if row["is_anomalous"] == 1 else "green",
            "size": round((row["total_incoming"] + row["total_outgoing"]) ** 0.5, 2),
            "height": round(max(anomaly_score, 0) * 10, 2),  
            "is_anomalous": int(row["is_anomalous"])
        })

    # ---------- Links ----------
    links = []
    for _, row in tx_df.iterrows():
        links.append({
            "source": int(row["source"]),
            "target": int(row["target"]),
            "amount": float(row["amount"])
        })

    graph = {
        "nodes": nodes,
        "links": links
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(graph, f, indent=2)

    print(f" Visualization graph ready → {OUTPUT_FILE}")
    print(f" Nodes: {len(nodes)} | Links: {len(links)}")

if __name__ == "__main__":
    prepare_viz_data()
