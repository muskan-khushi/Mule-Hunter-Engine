import numpy as np
from sklearn.ensemble import IsolationForest

# Simple EIF model
model = IsolationForest(
    n_estimators=200,
    contamination=0.05,
    random_state=42
)

def score_eif(features: dict):

    X = np.array([[
        features.get("velocity",0),
        features.get("burst",0),
        features.get("deviceReuse",0),
        features.get("ja3Reuse",0),
        features.get("ipReuse",0)
    ]])

    raw = -model.decision_function(X)[0]

    score = max(0,min(1,raw))

    return float(score)