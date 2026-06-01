import json
import joblib
from pathlib import Path

MODEL_DIR = Path("output/model")

km_model = joblib.load(MODEL_DIR / "kmeans.pkl")
scaler = joblib.load(MODEL_DIR / "scaler.pkl")
feature_cols = joblib.load(MODEL_DIR / "feature_cols.pkl")
with open(MODEL_DIR / "cluster_profiles.json", encoding="utf-8") as f:
    cluster_profiles = json.load(f)

# Export everything needed to JS
export_data = {
    "cluster_centers": km_model.cluster_centers_.tolist(),
    "scaler_mean": scaler.mean_.tolist(),
    "scaler_scale": scaler.scale_.tolist(),
    "feature_cols": list(feature_cols),
    "cluster_profiles": cluster_profiles
}

with open("public/model_data.json", "w", encoding="utf-8") as f:
    json.dump(export_data, f)

print("Exported model data to public/model_data.json")
