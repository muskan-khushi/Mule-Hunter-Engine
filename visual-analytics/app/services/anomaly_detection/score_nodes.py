from typing import Dict, List, Tuple

from app.services.anomaly_detection.eif_detector import (
    train_isolation_forest,
    score_nodes as _score_nodes,
)


def score_single_node(
    enriched_node: Dict,
    reference_nodes: List[Dict],
) -> Tuple[float, int]:
    """
    Scores ONE node relative to a reference population.

    Returns:
        anomaly_score (float)
        is_anomalous (int: 0 or 1)
    """

    # Safety: unsupervised ML is meaningless on tiny populations
    if not reference_nodes or len(reference_nodes) < 10:
        return 0.0, 0

    # Train model on reference population
    model, scaler = train_isolation_forest(reference_nodes)

    print("📐 Population size used for scoring:", len(reference_nodes))

    # Score ONLY the target node
    scores = _score_nodes(
        model=model,
        scaler=scaler,
        nodes=[enriched_node],
    )

    if not scores:
        return 0.0, 0

    result = scores[0]

    return (
        float(result["anomaly_score"]),
        int(result["is_anomalous"])   # 🔑 THIS IS THE FIX
    )
