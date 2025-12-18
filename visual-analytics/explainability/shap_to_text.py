import json
import os
from explanation_mapper import FEATURE_EXPLANATIONS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "shared-data"))

INPUT_FILE = os.path.join(SHARED_DATA_DIR, "shap_explanations.json")
OUTPUT_FILE = os.path.join(SHARED_DATA_DIR, "fraud_explanations.json")


def generate_human_explanations():
    with open(INPUT_FILE, "r") as f:
        shap_data = json.load(f)

    explanations_output = []

    for node in shap_data:
        node_id = node["node_id"]
        reasons = []

        for feature_info in node["top_factors"]:
            feature = feature_info["feature"]
            value = feature_info["impact"]

            if feature in FEATURE_EXPLANATIONS:
                reason = (
                    FEATURE_EXPLANATIONS[feature]["positive"]
                    if value > 0
                    else FEATURE_EXPLANATIONS[feature]["negative"]
                )
                reasons.append(reason)

        explanations_output.append({
            "node_id": node_id,
            "reasons": reasons
        })

    with open(OUTPUT_FILE, "w") as f:
        json.dump(explanations_output, f, indent=2)

    print(f" Human-readable explanations saved → {OUTPUT_FILE}")


if __name__ == "__main__":
    generate_human_explanations()
