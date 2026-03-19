"""
EIF Training Pipeline  —  Fixed v5
====================================

Bugs fixed vs previous version:
  [1] INVERTED SCORING DIRECTION (critical)
      eif.iForest.compute_paths() returns average PATH LENGTH.
      Shorter path = easier to isolate = ANOMALY.
      Longer path  = harder to isolate = NORMAL.

      Previous code:
          threshold = np.percentile(scores, 95)   # 95th percentile = LONG paths = NORMAL end
          preds = (scores >= threshold)            # flagged LONGEST paths = most NORMAL = WRONG

      Fixed:
          threshold = np.percentile(scores, 5)    # 5th percentile = SHORT paths = anomaly end
          preds = (scores <= threshold)            # flag SHORTEST paths = most anomalous = CORRECT

  [2] AUC calculation was also inverted.
      roc_auc_score(y, scores) where scores=path_lengths and shorter=fraud
      → higher score did NOT correlate with fraud → AUC was reporting ~0.3 (inverted model)
      Fix: pass -scores so higher value = more anomalous = correct AUC direction.

  [3] Threshold saved to metadata is now the CORRECT anomaly threshold (5th percentile),
      which inference.py reads and uses in its sigmoid formula.
"""

import pandas as pd
import numpy as np
import joblib
import json
from pathlib import Path

from eif import iForest
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score


# ──────────────────────────────────────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────────────────────────────────────

# train_eif.py lives at: .../visual-analytics/eif_v_2/train/train_eif.py
# parents[0] = train/
# parents[1] = eif_v_2/
# parents[2] = visual-analytics/
# parents[3] = <project_root>/
BASE_DIR = Path(__file__).resolve().parents[3]

DATA_PATH  = BASE_DIR / "shared-data" / "eif_features.csv"
MODEL_DIR  = BASE_DIR / "visual-analytics" / "eif_v_2" / "models"

SCALER_PATH     = MODEL_DIR / "eif_scaler.pkl"
TRAIN_DATA_PATH = MODEL_DIR / "eif_training_data.npy"
EVAL_PATH       = MODEL_DIR / "eif_eval.json"
META_PATH       = MODEL_DIR / "model_metadata.json"


# ──────────────────────────────────────────────────────────────────────────────
# RAW FEATURES  (ORDER IS CONTRACT — must match inference.py expand_features)
# ──────────────────────────────────────────────────────────────────────────────

RAW_FEATURES = [
    "velocity_score",
    "burst_score",
    "suspicious_neighbor_count",
    "ja3_reuse_count",
    "device_reuse_count",
    "ip_reuse_count",
]


# ──────────────────────────────────────────────────────────────────────────────
# FEATURE EXPANSION  (must stay identical to inference.py expand_features)
# ──────────────────────────────────────────────────────────────────────────────

def expand_features(row):
    velocity  = row["velocity_score"]
    burst     = row["burst_score"]
    neighbors = row["suspicious_neighbor_count"]
    ja3       = row["ja3_reuse_count"]
    device    = row["device_reuse_count"]
    ip        = row["ip_reuse_count"]

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


FEATURE_NAMES = [
    "velocity", "burst", "neighbors",
    "ja3", "device", "ip",
    "infra_risk", "velocity_burst", "neighbor_velocity",
    "device_ip", "ja3_weighted", "burst_neighbor",
]


# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE
# ──────────────────────────────────────────────────────────────────────────────

print("\n🚀 Starting EIF Training Pipeline\n")

# Load data
print("📂 Loading dataset:", DATA_PATH)
df = pd.read_csv(DATA_PATH)
print("Dataset shape:", df.shape)

# Validate
missing = [f for f in RAW_FEATURES if f not in df.columns]
if missing:
    raise ValueError(f"Missing features in CSV: {missing}")
print("✅ All required features present")

# Clean
df = df.replace([np.inf, -np.inf], np.nan).fillna(0)

# Expand features
print("\n⚙️  Expanding features")
expanded = df.apply(expand_features, axis=1, result_type="expand")
expanded.columns = FEATURE_NAMES
X = expanded.values
y = df["is_fraud"].values if "is_fraud" in df.columns else None
print("Expanded feature dimension:", X.shape)

# Scale
print("\n⚙️  Applying RobustScaler")
scaler   = RobustScaler()
X_scaled = scaler.fit_transform(X)

# Train EIF
print("\n🧠 Training Extended Isolation Forest")
model = iForest(
    X_scaled,
    ntrees=500,
    sample_size=min(256, len(X_scaled)),
    ExtensionLevel=1,
)

# Compute path lengths
# compute_paths() returns AVERAGE PATH LENGTH:
#   SHORT path → easy to isolate → ANOMALY  (mule / fraud account)
#   LONG  path → hard to isolate → NORMAL   (legitimate account)
scores = np.array(model.compute_paths(X_scaled))

print("\n📊 Path-length statistics (shorter = more anomalous)")
print("  min  (most anomalous):", round(scores.min(), 4))
print("  max  (most normal):   ", round(scores.max(), 4))
print("  mean:                 ", round(scores.mean(), 4))

# ── [FIX 1] Threshold at 5th percentile (SHORT paths = anomalies) ──────────
# The previous code used the 95th percentile, which is the NORMAL end of the
# distribution. That caused legitimate transactions to be flagged as fraud and
# genuine anomalies to receive near-zero scores.
threshold = float(np.percentile(scores, 5))
print(f"\n🎯 Anomaly threshold (5th percentile of path lengths): {threshold:.4f}")
print("   Samples with path_length <= threshold are flagged as anomalous.")

# Save artifacts
MODEL_DIR.mkdir(parents=True, exist_ok=True)
joblib.dump(scaler, SCALER_PATH)
np.save(TRAIN_DATA_PATH, X_scaled)
print("\n💾 Scaler saved:        ", SCALER_PATH)
print("💾 Training data saved: ", TRAIN_DATA_PATH)

# ── Evaluation ────────────────────────────────────────────────────────────────
metrics = {}

if y is not None:
    print("\n📈 Running evaluation")

    # [FIX 1] Flag SHORT paths (anomalies), not LONG paths (normals)
    preds = (scores <= threshold).astype(int)

    f1        = f1_score(y, preds, zero_division=0)
    precision = precision_score(y, preds, zero_division=0)
    recall    = recall_score(y, preds, zero_division=0)

    # [FIX 2] AUC: negate scores so higher value = more anomalous = correct direction
    # roc_auc_score expects: higher score → more likely positive (fraud)
    # With raw path lengths, shorter = fraud = LOWER score → negate to flip direction
    auc = roc_auc_score(y, -scores)

    metrics = {
        "f1":        float(f1),
        "precision": float(precision),
        "recall":    float(recall),
        "auc":       float(auc),
        "threshold": threshold,
    }

    with open(EVAL_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\n📊 Evaluation Metrics")
    print(f"  F1:        {f1:.4f}")
    print(f"  Precision: {precision:.4f}")
    print(f"  Recall:    {recall:.4f}")
    print(f"  AUC:       {auc:.4f}")

else:
    metrics = {"threshold": threshold}
    print("\n⚠️  No labels found — skipping evaluation.")

# Metadata
metadata = {
    "model":                "EIF",
    "version":              "v5",
    "raw_feature_dim":      len(RAW_FEATURES),
    "expanded_feature_dim": len(FEATURE_NAMES),
    "threshold":            threshold,          # 5th percentile — anomaly end
    "threshold_direction":  "lte",              # path_length <= threshold → fraud
    "raw_features":         RAW_FEATURES,
    "expanded_features":    FEATURE_NAMES,
}

with open(META_PATH, "w") as f:
    json.dump(metadata, f, indent=2)

print("\n📦 Metadata saved:", META_PATH)

# Debug sample
print("\n🔬 Sample path lengths (shorter = more anomalous)")
for i in range(min(5, len(scores))):
    flag = "⚠ ANOMALY" if scores[i] <= threshold else "✓ normal"
    print(f"  sample {i}: path={scores[i]:.4f}  {flag}")

print("\n✅ EIF Training Complete\n")