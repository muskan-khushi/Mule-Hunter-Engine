import logging
import httpx
from app.config import BACKEND_BASE_URL, REQUEST_TIMEOUT


# INTERNAL SAFE POST


async def _post_safe(url: str, data):
    """
    Async backend POST with timeout + error isolation.
    Never crashes pipeline.
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            await client.post(url, json=data)
            logging.info(f"POST success → {url}")
    except Exception as e:
        logging.error(f"POST failed → {url} | {e}")



# READ (NODE-SCOPED)


async def fetch_all_enriched_nodes():
    """
    Fetch ALL enriched nodes.
    Used as reference population for ML training.
    """
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get(
            f"{BACKEND_BASE_URL}/backend/api/nodes/enriched"
        )

        if not resp.is_success:
            logging.error(
                f"Failed to fetch enriched nodes "
                f"[{resp.status_code}]: {resp.text}"
            )
            return []

        return resp.json()





# WRITE (NODE-SCOPED)


async def post_anomaly_score(node_id: int, score: float):
    await _post_safe(
        f"{BACKEND_BASE_URL}/backend/api/visual/anomaly-scores/batch",
        [{
            "nodeId": node_id,
            "anomalyScore": score,
            "isAnomalous": 1 if score > 0 else 0,   
            "model": "eif_v1",
            "source": "visual-analytics"
        }]
    )


async def post_shap_explanation(payload: dict):
    await _post_safe(
        f"{BACKEND_BASE_URL}/backend/api/visual/shap-explanations/batch",
        [{
            "nodeId": payload["node_id"],
            "anomalyScore": payload["anomaly_score"],
            "topFactors": payload["top_factors"],
            "model": payload.get("model", "shap_v1"),
            "source": payload.get("source", "visual-analytics"),
        }]
    )





async def post_fraud_explanation(node_id: int, reasons: list):
    await _post_safe(
        f"{BACKEND_BASE_URL}/backend/api/visual/fraud-explanations/batch",
        [
            {
                "nodeId": node_id,
                "reasons": reasons,
                "model": "rules_v1",
                "source": "visual-analytics"
            }
        ]
    )

