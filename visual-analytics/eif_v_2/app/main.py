from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .schemas import EIFRequest
from .inference import score_eif

app = FastAPI()


@app.post("/v1/eif/score")
def score_endpoint(req: EIFRequest):

    score, top_factors, explanation = score_eif(req.features)

    # Confidence = distance from the decision boundary (0.5), mapped to [0, 1].
    # score=0.50 → 0.00 (maximally uncertain)
    # score=0.80 → 0.60 (reasonably confident fraud)
    # score=0.05 → 0.90 (confidently clean)
    confidence = round(abs(float(score) - 0.5) * 2, 3)

    return JSONResponse(
        content={
            "model": "EIF",
            "version": "v2.1",
            "score": float(score),
            "confidence": confidence,
            "topFactors": {
                k: float(v) for k, v in top_factors.items()
            },
            "explanation": explanation
        }
    )