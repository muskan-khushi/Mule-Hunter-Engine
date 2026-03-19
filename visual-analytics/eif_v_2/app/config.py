from pathlib import Path

# app/config.py lives at: .../visual-analytics/eif_v_2/app/config.py
# parents[0] = app/
# parents[1] = eif_v_2/   ← project root for this service
BASE_DIR = Path(__file__).resolve().parents[1]

# BUG FIX: export MODEL_DIR so inference.py can use it for absolute paths.
# Previously inference.py hardcoded TRAIN_DATA_PATH = "models/eif_training_data.npy"
# as a RELATIVE path. When uvicorn is started from any directory other than eif_v_2/,
# np.load() throws FileNotFoundError at module load time, crashing the entire service
# silently — EifService.onErrorResume() catches it and returns score=0.0 every time.
MODEL_DIR = BASE_DIR / "models"

MODEL_PATH    = MODEL_DIR / "eif_model.pkl"
SCALER_PATH   = MODEL_DIR / "eif_scaler.pkl"
METADATA_PATH = MODEL_DIR / "model_metadata.json"

# Raw feature names match train_eif.py RAW_FEATURES exactly — ORDER IS CONTRACT.
FEATURE_NAMES = [
    "velocity_score",
    "burst_score",
    "suspicious_neighbor_count",
    "ja3_reuse_count",
    "device_reuse_count",
    "ip_reuse_count"
]

FEATURE_EXPLANATIONS = {
    "velocity_score":             "High transaction velocity detected",
    "burst_score":                "Sudden burst of transactions observed",
    "suspicious_neighbor_count":  "Account connected to suspicious accounts in the network",
    "ja3_reuse_count":            "TLS fingerprint reused across multiple accounts",
    "device_reuse_count":         "Device used by multiple accounts",
    "ip_reuse_count":             "IP address shared across many users",
}