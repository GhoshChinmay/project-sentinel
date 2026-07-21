# Project Sentinel — Merge Notes

This folder is the **unified** Project Sentinel, combining two forks that were built
on the same skeleton by two people on two machines:

- **Mac fork** (`../project-sentinel`) — Counterfeit Currency + Fraud Graph.
- **Windows fork** (`../project-sentinel-main`) — Digital Arrest NLP/Audio + GCPI.

Both original folders are left untouched as reference/fallback.

## Feature ownership (as merged)

| # | Pillar | From | Key files |
|---|--------|------|-----------|
| 1 | Digital Arrest Scam Detection (+ audio deepfake) | Windows | `nlp_engine.py` (Groq), `rules_engine.py`, `audio_engine.py`, WebSocket |
| 2 | Counterfeit Currency ID | Mac | `vision_engine.py` (OpenRouter), `cv_engine.py` |
| 3 | Fraud Network Graph | Mac | `graph_engine.py`, `evidence_engine.py`, `correlation_engine.py` |
| 4 | Geospatial Crime Pattern (GCPI) | Windows | `geo_engine.py`, `gcpi_engine.py` |

## How the merge was done (preserve-logic principle)

- **Feature engines were copied byte-for-byte** from their owning fork — no logic changes.
- Only **5 "seam" files** were hand-merged as additive unions:
  - `models.py` — union schema: Mac's `Campaign` table + graph columns **and** Windows' `GeoEvent` table.
  - `main.py` — all routes from both (uuid incident IDs, Mac's enriched `/api/graph/full`, permissive CORS).
  - `correlation_engine.py` — keeps Mac's jurisdiction/lead-time/graph-hook **and** Windows' degree-centrality/Sybil/mule metrics in one return dict.
  - `seed_data.py` — Mac's 3 campaigns + fund-flow edges **and** Windows' 253 GCPI geo-events; runs graph analysis so campaigns populate.
  - `requirements.txt` — union of both dependency sets.
- **LLM providers are split by feature:** `vision_engine` uses **OpenRouter**, `nlp_engine` uses **Groq**. Both SDKs coexist.
- **Compatibility fixes made for this machine (Python 3.9):**
  - `nlp_engine.py` now boots gracefully with **no `GROQ_API_KEY`** — it runs deterministic-only (rules + local V.A.D.). Cloud logic is unchanged when the key is present.
  - `geo_engine.py` got `from __future__ import annotations` so its `str | None` hints parse on Python 3.9.
  - Frontend currency tab (`App.jsx`) made object-aware for Mac's `forgery_markers` (`{label, status}`).
  - **Currency scanner (Feature 2) is Mac's full component** — ported in, including **live auto-capture** (motion-detection on a hidden 64×64 canvas; auto-captures once a note is held steady ~2s with a "Hold steady…" countdown), targeting overlay, portrait-identity check, denomination, and anomaly bounding boxes. Fetch URL made absolute.
  - Fixed a latent Windows-fork bug: `App.jsx` used `FingerprintIcon` without importing it (aliased `Fingerprint as FingerprintIcon`).

## Prerequisite

Add a free **Groq key** to `backend/.env` for full cloud scam-call analysis
(get one at https://console.groq.com/keys):

```
GROQ_API_KEY=gsk_...
```

Without it, Feature 1 still works in deterministic mode. The OpenRouter key
(Feature 2) is already present.

## Run it

```bash
# Backend
cd backend
python3 -m venv venv                 # already created
./venv/bin/pip install -r requirements.txt
./venv/bin/python seed_data.py       # builds sentinel.db (campaigns + geo events)
./venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

Backend: http://127.0.0.1:8000  (Swagger at `/docs`)

## Verified end-to-end (2026-07-21)

- **Feature 1:** `/api/analyze` → digital-arrest script = critical 98%, safe family chat = safe 99%; `/api/analyze-audio` on `deepfake_scam.wav` = deepfake 99.5%; `/ws/live-audio` WebSocket round-trips.
- **Feature 2:** `/api/scan-document` (OpenRouter) returns structured `forgery_markers` + cv/dl metrics.
- **Feature 3:** `/api/graph/full` = 15 nodes / 3 campaigns with centrality; `/api/evidence/generate` returns SHA-256 dossier.
- **Feature 4:** `/api/gcpi/full` returns full pipeline; `/api/gcpi/stats` = 253 events across 15 cities.
- Frontend production build + dev server both succeed.

DB row counts after seed: campaigns 3, entities 15, incidents 40, graph_edges 15, geo_events 253.
