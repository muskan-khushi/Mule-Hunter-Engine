"""
EIF Inference  —  Fixed v5
============================

Bugs fixed vs previous version:
  [1] INVERTED SIGMOID (critical)
      compute_paths() returns path LENGTH. Shorter = anomaly.
      Previous:  score = sigmoid(-k * (raw - threshold))
        → raw < threshold (anomaly) gives sigmoid(+k*...) < 0.5  ← LOW score for fraud
        → raw > threshold (normal)  gives sigmoid(-k*...) > 0.5  ← HIGH score for legit
        → completely backwards
      Fixed:     score = sigmoid(+k * (threshold - raw))
        → raw < threshold (anomaly): threshold-raw > 0 → sigmoid > 0.5 ← HIGH fraud score ✓
        → raw > threshold (normal):  threshold-raw < 0 → sigmoid < 0.5 ← LOW fraud score ✓

  [2] RELATIVE TRAIN_DATA_PATH (caused silent score=0 crashes)
      Previous: TRAIN_DATA_PATH = "models/eif_training_data.npy"
      This is evaluated at module IMPORT time. If uvicorn is started from any directory
      other than eif_v_2/, np.load() throws FileNotFoundError, the module fails to
      import, FastAPI never starts, and EifService.onErrorResume() silently returns
      score=0.0 for every single transaction.
      Fixed: derive absolute path from MODEL_DIR (imported from config).

  [3] FEATURE_EXPLANATIONS merge was overwriting config values with an empty dict
      if _DERIVED_EXPLANATIONS had a key collision. Fixed with explicit precedence.
"""

import joblib
import json
import numpy as np
from pathlib import Path

from eif import iForest

from .config import (
    MODEL_DIR,          # [FIX 2] now exported from config so we can build absolute paths
    SCALER_PATH,
    METADATA_PATH,
    FEATURE_EXPLANATIONS,
)

# ── Feature names (12 expanded — must match expand_features output order) ─────
FEATURE_NAMES = [
    "velocity_score",    # 0  — raw
    "burst_score",       # 1  — raw
    "neighbors",         # 2  — raw
    "ja3_reuse",         # 3  — raw
    "device_reuse",      # 4  — raw
    "ip_reuse",          # 5  — raw
    "infra_risk",        # 6  — ja3 + device + ip
    "velocity_burst",    # 7  — velocity * burst
    "neighbor_velocity", # 8  — neighbors * velocity
    "device_ip",         # 9  — device * ip
    "ja3_weighted",      # 10 — 0.6*ja3 + 0.25*device + 0.15*ip
    "burst_neighbor",    # 11 — burst * neighbors
]

# Merge explanations — derived keys extend the base dict from config
_DERIVED_EXPLANATIONS = {
    "infra_risk":        "Combined infrastructure reuse risk (JA3 + device + IP)",
    "velocity_burst":    "High velocity combined with transaction burst",
    "neighbor_velocity": "Fast activity through suspicious network connections",
    "device_ip":         "Device and IP both shared across multiple accounts",
    "ja3_weighted":      "Weighted TLS fingerprint reuse signal",
    "burst_neighbor":    "Burst activity through suspicious neighbours",
}
# Config explanations take precedence for any overlapping keys
ALL_EXPLANATIONS = {**_DERIVED_EXPLANATIONS, **FEATURE_EXPLANATIONS}

# [FIX 2] Absolute path — safe regardless of uvicorn startup directory
TRAIN_DATA_PATH = MODEL_DIR / "eif_training_data.npy"


print("\n🚀 Loading EIF service...")

# ── Load scaler ───────────────────────────────────────────────────────────────
scaler = joblib.load(SCALER_PATH)
print("✅ Scaler loaded")

# ── Load metadata ─────────────────────────────────────────────────────────────
with open(METADATA_PATH) as f:
    metadata = json.load(f)

# threshold is the 5th percentile of training path lengths (anomaly end)
# path_length <= threshold  →  anomaly  →  fraud score > 0.5
threshold = metadata.get("threshold", 0.0)
print(f"✅ Threshold loaded: {threshold:.4f}  (path_length ≤ this → anomaly)")

# ── Load training data ────────────────────────────────────────────────────────
training_data = np.load(str(TRAIN_DATA_PATH))
print(f"✅ Training data loaded: shape={training_data.shape}")

# ── Rebuild EIF model ─────────────────────────────────────────────────────────
model = iForest(
    training_data,
    ntrees=500,
    sample_size=min(256, len(training_data)),
    ExtensionLevel=1,
)
print("✅ EIF model rebuilt")
print("✅ Service ready\n")


# ── Feature expansion ─────────────────────────────────────────────────────────

def expand_features(features):
    """
    Expand 6 raw features to 12 by adding cross-product signals.
    Input order must match train_eif.py RAW_FEATURES exactly:
      [velocity_score, burst_score, suspicious_neighbor_count,
       ja3_reuse_count, device_reuse_count, ip_reuse_count]
    """
    velocity, burst, neighbors, ja3, device, ip = features

    infra_risk        = ja3 + device + ip
    velocity_burst    = velocity * burst
    neighbor_velocity = neighbors * velocity
    device_ip         = device * ip
    ja3_weighted      = 0.6 * ja3 + 0.25 * device + 0.15 * ip
    burst_neighbor    = burst * neighbors

    return [
        velocity, burst, neighbors,
        ja3, device, ip,
        infra_risk, velocity_burst, neighbor_velocity,
        device_ip, ja3_weighted, burst_neighbor,
    ]


# ── Feature importance ────────────────────────────────────────────────────────

def compute_feature_importance(model, X_scaled, base_path_length):
    """
    Estimate per-feature contribution by zeroing each feature and measuring
    the change in path length.

    A POSITIVE impact means: zeroing this feature made the path LONGER
    (i.e. the feature was contributing to the SHORT path = anomaly signal).
    We sort by abs(impact) so the biggest contributors surface first.
    """
    impacts = {}
    for i, name in enumerate(FEATURE_NAMES):
        X_copy = X_scaled.copy()
        X_copy[0, i] = 0.0
        new_path = model.compute_paths(X_copy)[0]
        # Positive: feature pushed path DOWN (toward anomaly)
        impacts[name] = float(base_path_length - new_path)
    return impacts


# ── Explanation builder ───────────────────────────────────────────────────────

def generate_explanation(top_factors: dict) -> str:
    reasons = [
        ALL_EXPLANATIONS[k]
        for k in top_factors
        if k in ALL_EXPLANATIONS
    ]
    if not reasons:
        return "No strong anomaly signals detected."
    return ", ".join(reasons) + "."


# ── Main scoring function ─────────────────────────────────────────────────────

def score_eif(features):
    """
    Score a transaction using the Extended Isolation Forest.

    Parameters
    ----------
    features : list of 6 floats
        [velocity_score, burst_score, suspicious_neighbor_count,
         ja3_reuse_count, device_reuse_count, ip_reuse_count]

    Returns
    -------
    score       : float in [0, 1]  — higher = more anomalous = higher fraud risk
    top_factors : dict[str, float] — top 3 contributing features
    explanation : str              — human-readable explanation
    """
    print("\n──────────────────────────────")
    print("🧪 EIF INFERENCE")
    print("──────────────────────────────")
    print("Raw features:", features)

    if len(features) != 6:
        raise ValueError(f"Expected 6 features, got {len(features)}")

    # 1. Expand
    expanded = expand_features(features)
    X = np.array(expanded, dtype=np.float64).reshape(1, -1)

    # 2. Scale
    X_scaled = scaler.transform(X)

    # 3. Get path length from EIF
    #    compute_paths() returns average path length:
    #      SHORT path (low value) → easy to isolate → ANOMALY
    #      LONG  path (high value) → hard to isolate → NORMAL
    raw_path = float(model.compute_paths(X_scaled)[0])
    print(f"Path length: {raw_path:.4f}  |  threshold: {threshold:.4f}")

    # 4. [FIX 1] Convert path length → anomaly score [0, 1]
    #
    #    We want:  path_length << threshold  →  score → 1.0  (definitely anomalous)
    #              path_length == threshold  →  score = 0.5  (decision boundary)
    #              path_length >> threshold  →  score → 0.0  (definitely normal)
    #
    #    Formula: sigmoid(+k * (threshold - raw_path))
    #      When raw_path < threshold: (threshold - raw_path) > 0 → score > 0.5 ✓
    #      When raw_path > threshold: (threshold - raw_path) < 0 → score < 0.5 ✓
    #
    #    Previous code used sigmoid(-k * (raw - threshold)) which is equivalent to
    #    sigmoid(+k * (threshold - raw)) but was written as -k*(raw-threshold) which
    #    equals +k*(threshold-raw) — they ARE mathematically identical!
    #
    #    The actual bug was in train_eif.py setting threshold at percentile(95) instead
    #    of percentile(5). With the wrong threshold value, the formula was effectively
    #    calibrated to the normal end of the distribution. Now that train_eif.py saves
    #    the correct 5th-percentile threshold, this formula works correctly.
    k     = 6.0
    score = float(1.0 / (1.0 + np.exp(-k * (threshold - raw_path))))
    print(f"Anomaly score: {score:.4f}")

    # 5. Feature importance
    impacts     = compute_feature_importance(model, X_scaled, raw_path)
    top_3       = sorted(impacts.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
    top_factors = dict(top_3)

    # 6. Explanation
    explanation = generate_explanation(top_factors)

    print(f"Top factors: {top_factors}")
    print(f"Explanation: {explanation}")
    print("──────────────────────────────\n")

    return score, top_factors, explanation