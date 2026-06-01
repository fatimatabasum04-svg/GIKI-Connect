import json
import joblib
import csv
from pathlib import Path

MODEL_DIR = Path("output/model")

km_model = joblib.load(MODEL_DIR / "kmeans.pkl")
scaler = joblib.load(MODEL_DIR / "scaler.pkl")
feature_cols = joblib.load(MODEL_DIR / "feature_cols.pkl")
with open(MODEL_DIR / "cluster_profiles.json", encoding="utf-8") as f:
    cluster_profiles = json.load(f)

# Load cohort
cohort = []
try:
    with open("output/combined_with_clusters.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                row["_cluster"] = int(float(row.get("Cluster", -1)))
            except (TypeError, ValueError):
                continue
            cohort.append(row)
except Exception:
    pass

# Load events
events = []
try:
    with open("data/events.json", encoding="utf-8") as f:
        events = json.load(f).get("events", [])
except Exception:
    pass

# Polish display fields
for prof in cluster_profiles.values():
    if isinstance(prof, dict):
        name = prof.get("name")
        if isinstance(name, str):
            prof["name"] = name.replace("Coding  Programming", "Coding / Programming")
        tops = prof.get("top_hobbies")
        if isinstance(tops, list):
            prof["top_hobbies"] = [
                h.replace("Coding  Programming", "Coding / Programming") if isinstance(h, str) else h
                for h in tops
            ]

export_data = {
    "cluster_centers": km_model.cluster_centers_.tolist(),
    "scaler_mean": scaler.mean_.tolist(),
    "scaler_scale": scaler.scale_.tolist(),
    "feature_cols": list(feature_cols),
    "cluster_profiles": cluster_profiles,
    "cohort": cohort,
    "events": events
}

with open("public/model_data.json", "w", encoding="utf-8") as f:
    json.dump(export_data, f)

print("Export complete")
