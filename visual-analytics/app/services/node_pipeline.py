from typing import List

from app.services.anomaly_detection.score_nodes import score_single_node
from app.services.explainability.explanation_mapper import build_fraud_explanation
from app.services.explainability.shap_runner import run_shap
from app.clients.backend_client import (
    fetch_all_enriched_nodes,
    post_anomaly_score,
    post_fraud_explanation,
    post_shap_explanation,
)



# NORMALIZATION (camelCase → snake_case)


def normalize_enriched_node(enriched: dict) -> dict:
    """
    Converts backend NodeEnriched payload into ML-safe schema.
    """
    return {
        "node_id": enriched.get("nodeId"),
        "in_degree": enriched.get("inDegree", 0),
        "out_degree": enriched.get("outDegree", 0),
        "total_incoming": enriched.get("totalIncoming", 0),
        "total_outgoing": enriched.get("totalOutgoing", 0),
        "risk_ratio": enriched.get("riskRatio", 0),
        "tx_velocity": enriched.get("txVelocity", 0),
        "account_age_days": enriched.get("accountAgeDays", 0),
        "balance": enriched.get("balance", 0),
    }



# FALLBACK SHAP FOR NORMAL NODES


def build_non_anomalous_shap(node_id: int, score: float) -> dict:
    """
    Placeholder explanation for non-anomalous nodes.
    """
    return {
        "node_id": node_id,
        "anomaly_score": round(float(score), 6),
        "top_factors": [
            {
                "feature": "overall",
                "impact": 0.0,
                "description": "No anomalous behavior detected"
            }
        ],
        "model": "baseline",
        "source": "shap"
    }



# MAIN PIPELINE (EVENT-DRIVEN)

async def run_node_pipeline(nodes: List):
    """
    Runs Visual-Analytics ML ONLY for nodes involved
    in a transaction event.
    """

    all_nodes = await fetch_all_enriched_nodes()

    if not all_nodes or len(all_nodes) < 10:
        print("Skipping ML: insufficient reference population")
        return

    normalized_population = [
        normalize_enriched_node(n)
        for n in all_nodes
        if n.get("nodeId") is not None
    ]

    print(" Total enriched nodes fetched:", len(all_nodes))

    for node in nodes:
        node_id = None

        try:
            node_id = node.nodeId
            if node_id is None:
                continue

            raw_node = next(
                (n for n in all_nodes if n.get("nodeId") == node_id),
                None
            )
            if not raw_node:
                continue

            target_node = normalize_enriched_node(raw_node)

            reference_nodes = [
                n for n in normalized_population
                if n["node_id"] != node_id
            ]

            if len(reference_nodes) < 10:
                continue

            #   ML CALL
            score, is_anomalous = score_single_node(
                enriched_node=target_node,
                reference_nodes=reference_nodes
            )

            print(
                f" FINAL DECISION | node={node_id} "
                f"score={score:.6f} "
                f"isAnomalous={is_anomalous}"
            )

            # Human explanation
            reasons = build_fraud_explanation(target_node, score)

            # SHAP
            if is_anomalous:
                print(" RUNNING SHAP for node:", node_id)
                shap_input = []

                #  Add NORMAL reference nodes
                for n in reference_nodes[:300]:  
                    shap_input.append({
                        **n,
                        "is_anomalous": 0,
                        "anomaly_score": 0.0,
                    })

                #  Add TARGET anomalous node LAST
                shap_input.append({
                    **target_node,
                    "is_anomalous": 1,
                    "anomaly_score": score,
                })

                print(" SHAP INPUT SIZE =", len(shap_input))
                print(" SHAP y.sum() =", sum(x["is_anomalous"] for x in shap_input))

                shap_results = run_shap(shap_input)
                print(" SHAP RESULTS RAW =", shap_results)


            else:
                shap_results = [
                    build_non_anomalous_shap(node_id, score)
                ]

            # Persist
            await post_anomaly_score(node_id, score)
            await post_fraud_explanation(node_id, reasons)

            for shap in shap_results:
                await post_shap_explanation({
                    "node_id": shap["node_id"],
                    "anomaly_score": shap["anomaly_score"],
                    "top_factors": shap["top_factors"],
                    "model": shap.get("model", "shap_v1"),
                    "source": "visual-analytics",
                })

            print(f" Visual ML completed for node {node_id}")

        except Exception as e:
            print(f" Visual ML failed for node {node_id}: {str(e)}")
