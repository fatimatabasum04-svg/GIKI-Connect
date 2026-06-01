# GIKI-Connect

**Analyzing social siloing and the “society bridge” in a residential campus** · Theory of Data Science · Fatima Tabasum (2024178) · Saadia Asghar (2024550) · Instructor: Sir Shahab Ansari

| Piece | What it shows |
| --- | --- |
| **`GIKI_Connect_Notebook.ipynb`** | Chi-square (society membership × silo band); Pearson (society hours vs silo); **K-Means** interest tribes; figures + pickles in `output/model/`. |
| **Web app** | Student **suggestions** (events + anonymized “say hi” ideas); **GIKI admin** posts mixers in `data/events.json` using tribe IDs + hobby tags—same tribe assignment as the notebook. |

**GitHub:** [Saadia-Asghar/Giki-Connect](https://github.com/Saadia-Asghar/Giki-Connect)

## Is the app really using the trained model?

**Yes.** On each “Find my interest tribe” request the server:

1. Builds the same feature row as the notebook (`h_*` hobby columns + `SocHours`, `ComfortScore`, **`Silo_Index`** = report silo: (friends same province **or** same faculty) ÷ total friends — from survey % we use **p + f − p×f** with p,f on 0–1; **friends** count 1–20. If the student picks **not a society member**, society hours are treated as **0** for the model (society bridge logic).
2. Runs `scaler.transform(...)` then `kmeans.predict(...)` on **`output/model/scaler.pkl`** and **`output/model/kmeans.pkl`** (joblib).

**Faculty, year, and society names** are collected in the live demo for realism and your report narrative; they are **not** inputs to the current K-Means vector (retraining would be needed to include them).

Event and peer suggestions are **on top of** that prediction (rules + CSV), not a replacement for the model.

`GET /api/meta` returns cohort size, tribe count, plus faculty/year dropdown options from `combined_with_clusters.csv`.

## Run locally

```powershell
cd d:\hp2\Downloads\giki_project
pip install -r requirements.txt
python app_server.py
```

Or double-click **`START_APP.bat`**. Leave the console open while you use the app.

## Admin events

1. Open the app → **GIKI admin** tab — use **Interest tribes** (ids **0–7**, names from `cluster_profiles.json`) when posting.  
2. Default token: **`giki-admin-demo`** (override with env **`GIKI_ADMIN_TOKEN`**).  
3. Post title, time, place, description, **hobby tags**, and optionally **target tribes** so the right students see the event first.  
4. Events live in **`data/events.json`**. `GET /api/tribes` feeds the tribe cards + short “project context” copy on the student tab.

## Jupyter (retrain / refresh pickles)

```bash
pip install jupyter pandas numpy scikit-learn matplotlib scipy joblib openpyxl
jupyter notebook
```

Run `GIKI_Connect_Notebook.ipynb` top to bottom, then restart `app_server.py`.

If you only changed how **K-Means features** are defined but already have `output/merged_dataset.csv`, you can refresh pickles + `combined_with_clusters.csv` with:

`python scripts/refit_kmeans_from_merged.py`

## Deploy on Vercel

1. Import repo **Saadia-Asghar/Giki-Connect**, branch **main**.  
2. **Framework preset:** **Flask** (or leave auto-detect).  
3. **Root directory:** `.` (repo root). Leave **Output Directory** empty unless you know you need it — setting it to `public` will break the Python app.  
4. **Python:** 3.11 or newer on the project (matches `pyproject.toml` / `requirements.txt`).  
5. **Environment variables (optional):** `GIKI_ADMIN_TOKEN` = your secret (otherwise the default demo token is used).

Deployment follows Vercel’s **zero-config Flask** model: root **`app.py`** exposes the Flask instance `app` (`from app_server import app`). There is **no** `vercel.json` rewrite and **no** `api/index.py` — those patterns were causing **404** on production and preview URLs because routing never reached Flask’s `/` handler reliably.

**Static files:** keep **`public/`** at the repo root. Vercel serves those assets from the edge; **`GET /`** is still handled by Flask so the same `index.html` loads with consistent behaviour locally and in the cloud.

**Note:** Admin-posted events on Vercel are written under **`/tmp`** (ephemeral per serverless instance). For a real campus rollout, use a database or Vercel KV / Postgres. Cold starts load **scikit-learn** + pickles — the first request can take several seconds.

## Push

```bash
git add -A && git commit -m "message" && git push origin main
```
