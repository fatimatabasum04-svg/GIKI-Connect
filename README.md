#  GIKI-Connect

**Analyzing social siloing and the "society bridge" in a residential campus**

> Theory of Data Science · Fatima Tabasum (2024178) · Saadia Asghar (2024550)  
> Instructor: Sir Shahab Ansari

GIKI-Connect is a data science project + interactive web app that studies how GIKI students form friendships. It measures *social siloing* (the tendency to befriend people from the same province or faculty) and investigates whether society membership acts as a bridge across those silos. A K-Means clustering model groups students into **interest tribes**, and the live app uses those tribes to suggest relevant events and anonymized peer connections.

## 📋 Table of Contents

- [Research Background](#research-background)
- [How It Works](#how-it-works)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
- [Running the App](#running-the-app)
- [API Reference](#api-reference)
- [Admin: Posting Events](#admin-posting-events)
- [Retraining the Model](#retraining-the-model)
- [Deploying to Vercel](#deploying-to-vercel)
- [Contributing](#contributing)

## Research Background

GIKI is a fully residential campus, yet many students socialize primarily within their faculty, province, or batch — a pattern this project calls **social siloing**. The core hypothesis is that *shared hobbies and society participation* act as a natural bridge across these demographic boundaries.

The notebook tests this with:

- **Chi-square test** — society membership vs. silo band (are society members less siloed?)
- **Pearson correlation** — society hours vs. silo index (does more society time mean more diverse friendships?)
- **K-Means clustering** — groups students into 8 *interest tribes* based on their hobby profile, society hours, comfort score, and silo index

## How It Works

### Silo Index

The silo index is calculated from a student's self-reported friendship pattern:

```
Silo_Index = p + f − p × f
```

Where `p` = fraction of close friends from the same province and `f` = fraction from the same faculty. This estimates the proportion of close friends who share *either* demographic using a union approximation.

| Silo Value | Label |
|---|---|
| < 0.25 | Low (diverse) |
| 0.25 – 0.50 | Moderate |
| > 0.50 | High (siloed) |

### Tribe Assignment

On each "Find my interest tribe" request, the server:

1. Builds a feature vector from the user's hobby selections (`h_*` columns), `SocHours`, `ComfortScore`, and computed `Silo_Index`
2. Non-society members have their society hours set to **0**
3. Applies `scaler.transform(...)` then `kmeans.predict(...)` using the saved pickles in `output/model/`
4. Returns the matched tribe, personalized insight narrative, relevant events, and anonymized peer suggestions

Faculty, year, and society names are collected for realism and report narrative but **do not affect the tribe number** — they would require retraining to be model inputs.

## Features

| Component | Description |
|---|---|
| **Notebook** | Chi-square, Pearson, and K-Means analysis; saves `scaler.pkl`, `kmeans.pkl`, and `combined_with_clusters.csv` |
| **Tribe finder** | Student fills in hobbies, comfort, society status, and friendship sliders → assigned to an interest tribe |
| **Insight narrative** | Rule-based story blocks: key pointers, hobby-specific formats, society tips, cohort comparison, event shapes |
| **Event suggestions** | Ranked list of admin-posted events filtered by tribe + hobby tag overlap |
| **Peer suggestions** | Anonymized cohort members in the same tribe with the most hobby overlap |
| **Admin panel** | Post new events with title, time, place, hobby tags, and target tribe IDs |
| **Tribe atlas** | Overview of all 8 tribes with their top hobbies and admin guide |

## Tech Stack

- **Backend:** Python 3.11, Flask
- **ML:** scikit-learn (K-Means, StandardScaler), joblib
- **Data:** pandas, numpy, scipy, openpyxl
- **Frontend:** Vanilla HTML/CSS/JS (`index.html`)
- **Deployment:** Vercel (serverless Flask), Docker

## Project Structure

```
GIKI-Connect/
├── app_server.py              # Flask app — APIs and prediction logic
├── export_model.py            # Exports scaler + kmeans pickles to output/model/
├── export_model2.py           # Alternative export script
├── index.html                 # Single-page frontend
├── GIKI_Connect_Notebook.ipynb  # Full analysis: chi-square, Pearson, K-Means
├── GIKI_Connect_Data.xlsx     # Raw survey data
├── combined_with_clusters.csv # Cohort with assigned cluster labels (generated)
├── events.json                # Seed events (admin-posted events stored here locally)
├── model_data.json            # Serialized scaler + K-Means centroids for the server
├── requirements.txt           # Python dependencies
├── pyproject.toml             # Python version config
├── Dockerfile                 # Container setup
├── vercel.json                # Vercel deployment config
├── START_APP.bat              # Windows one-click launcher
├── serve.ps1                  # PowerShell launcher
└── output/
    ├── model/
    │   ├── scaler.pkl
    │   └── kmeans.pkl
    └── combined_with_clusters.csv
```

## Prerequisites

- Python 3.11+
- pip

## Local Setup

**1. Clone the repository**

```bash
git clone https://github.com/fatimatabasum04-svg/GIKI-Connect.git
cd GIKI-Connect
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Ensure model artifacts exist**

The `model_data.json` file (and optionally the `output/model/` pickles) must be present before running the server. If they are missing, run the notebook first (see [Retraining the Model](#retraining-the-model)) then re-export:

```bash
python export_model.py
```
## Running the App

**Option A — Python**

```bash
python app_server.py
```

**Option B — Windows batch file**

Double-click `START_APP.bat`. Keep the terminal window open while using the app.

**Option C — Docker**

```bash
docker build -t giki-connect .
docker run -p 8765:8765 giki-connect
```

The app auto-selects a free port starting at `8765` and opens the browser automatically. The console prints the URL and admin token.

## API Reference

All endpoints return JSON.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves the frontend (`index.html`) |
| `GET` | `/api/meta` | Cohort size, tribe count, faculty and year dropdown options |
| `GET` | `/api/tribes` | All tribe profiles + campus narrative for the student UI |
| `GET` | `/api/events` | List all posted events |
| `POST` | `/api/events` | Post a new event (admin token required) |
| `POST` | `/api/predict` | Submit a student profile and receive tribe assignment + suggestions |

### `POST /api/predict` — request body

```json
{
  "hobbies": ["Music", "Coding / Programming"],
  "soc_hours": 3.5,
  "comfort": 4,
  "same_prov_pct": 40,
  "same_fac_pct": 30,
  "friends": 6,
  "soc_member": true,
  "societies": "IEEE, Dramatics Society",
  "faculty": "CS",
  "year": "2nd Year"
}
```

Valid hobby values: `Music`, `Art`, `Cooking`, `Fitness`, `Football`, `Hiking`, `Coding / Programming`, `Reading`, `Debating`, `Gaming`, `Cricket`, `Photography`, `Travelling`, `Skating`.

## Admin: Posting Events

Events are secured by a token passed in the `X-Admin-Token` header.

**Default demo token:** `giki-admin-demo`  
**Override with env var:** `GIKI_ADMIN_TOKEN=your-secret`

```bash
curl -X POST http://127.0.0.1:8765/api/events \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: giki-admin-demo" \
  -d '{
    "title": "Cross-Faculty Coding Jam",
    "when_iso": "2025-03-15T14:00",
    "place": "CS Lab 3",
    "description": "Pair-programming sprint open to all faculties.",
    "hobby_tags": ["Coding / Programming", "Gaming"],
    "clusters": [3, 7]
  }'
```

- `clusters` — tribe IDs (0–7) to prioritize; leave empty to show to all tribes
- `hobby_tags` — must be valid hobby values from the list above
- Events are stored in `data/events.json` locally; on Vercel they live in `/tmp` (ephemeral per serverless instance)

## Retraining the Model

If you change the survey data or the feature definition, retrain via the notebook then re-export:

```bash
pip install jupyter pandas numpy scikit-learn matplotlib scipy joblib openpyxl
jupyter notebook
```

Open `GIKI_Connect_Notebook.ipynb` and run all cells top to bottom. Then restart `app_server.py`.

If you only changed the K-Means feature columns but already have `output/merged_dataset.csv`, refresh just the pickles and cluster CSV:

```bash
python scripts/refit_kmeans_from_merged.py
```
## Deploying to Vercel

1. Import the repo (`fatimatabasum04-svg/GIKI-Connect`, branch `main`)
2. **Framework preset:** Flask (or leave as auto-detect)
3. **Root directory:** `.` — leave Output Directory empty
4. **Python version:** 3.11 or newer (matches `pyproject.toml`)
5. **Environment variables (optional):** `GIKI_ADMIN_TOKEN` = your secret token

> **Note:** Admin-posted events on Vercel are written to `/tmp` and are ephemeral per serverless instance. For a production campus deployment, use a persistent database (Vercel KV or Postgres). Cold starts may take a few seconds due to scikit-learn and pickle loading.

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit and push: `git commit -m "Add feature" && git push origin feature/your-feature`
4. Open a Pull Request

```bash
git add -A && git commit -m "your message" && git push origin main
```
Theory of Data Science project — GIKI
