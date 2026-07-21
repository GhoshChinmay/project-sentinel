# PROJECT SENTINEL — Full Build Action Plan
**National Fraud Interdiction Grid — AI for Digital Public Safety**
Document purpose: hand this to a coding AI assistant (e.g. Claude Code) as the master build spec. Follow phases **in order** — each layer depends on the persistence/schema and correlation logic built in earlier phases.

---

## HOW TO USE THIS DOCUMENT

- Work top to bottom. Do not skip to frontend polish before the data layer exists — the graph, map, and citizen shield all read/write the same backend tables, so building them out of order causes rework.
- Every phase lists: **Goal**, **Tasks**, **Files touched**, **Definition of done**.
- Sections marked **🔴 MODEL REQUIRED FROM YOU** are places the coding AI cannot finish alone — you must supply a trained model, a dataset, or a decision. Everything else can be built end-to-end by the coding AI using Gemini + classical algorithms.
- Current codebase context: FastAPI backend (`backend/main.py`, `backend/nlp_engine.py`), React+Vite frontend (`frontend/src/App.jsx`, monolithic), Gemini 2.0 Flash for text + vision. No database. No geospatial module. Graph view is hardcoded demo data.

---

## PHASE 0 — Foundation & Persistence Layer
**Goal:** Replace in-memory state with a real, queryable data store. Every other phase writes to this.

### Tasks
1. Add SQLite (fast to ship, upgradeable to Postgres later — mention this upgrade path in the deck for "Scalability" scoring) via SQLAlchemy.
2. Design core tables:
   - `entities` (id, type: phone/upi_id/bank_account/device_id/ifsc, value, first_seen, risk_score)
   - `incidents` (id, type: scam_call/counterfeit_scan/citizen_report, timestamp, status, confidence, raw_payload_json, lat, lng, district)
   - `incident_entities` (incident_id, entity_id, role) — many-to-many join, this is what powers the graph
   - `graph_edges` (source_entity_id, target_entity_id, relationship_type, weight, created_at)
   - `evidence_packages` (id, incident_ids_json, generated_at, sha256_hash, pdf_path)
3. Write a seed script that generates realistic **synthetic historical data**: ~150 scam call incidents, ~40 counterfeit scans, ~200 citizen reports, all geo-tagged across 5-6 Indian cities/districts, with deliberately overlapping entities (same phone number appears in 3 different incidents, same UPI ID linked to 2 mule accounts) — this is what makes the graph and clustering demo look alive on stage instead of empty.
4. Refactor `main.py` endpoints to read/write through this DB instead of returning raw Gemini output only.

### Files touched
`backend/database.py` (new), `backend/models.py` (new), `backend/seed_data.py` (new), `backend/main.py` (refactor)

### Definition of done
Backend boots, DB file exists with seeded rows, `/api/analyze` and `/api/scan-document` write a new `incidents` row on every call instead of just returning JSON to the frontend.

---

## PHASE 1 — Entity Extraction & Correlation Engine
**Goal:** Turn every raw incident into structured entities that get linked across incidents. This is your core "convergence" differentiator — build this before touching the graph UI.

### Tasks
1. Extend `nlp_engine.py`: add a `extract_entities()` function. Prompt Gemini (structured JSON output, same pattern as existing classifiers) to pull phone numbers, UPI IDs, bank account/IFSC codes, and named institutions mentioned in a transcript or citizen chat message.
2. On every new incident, after entity extraction: check `entities` table for existing matches (exact match first; add fuzzy matching for phone number formatting variants later if time permits). Insert new entities or link to existing ones via `incident_entities`.
3. Build `correlation_engine.py`:
   - A function `run_community_detection()` using **NetworkX + the Louvain algorithm** (`python-louvain` package) over the `graph_edges` table to cluster entities into suspected fraud rings.
   - A function `compute_lead_time(incident_id)` — when a new incident correlates to an existing cluster with a "critical" incident already flagged, calculate and log the time delta between first flag and current time. This number is your headline demo metric ("fraud network detected 40 minutes before mass victimisation").
4. Add a scheduled/triggered job (simplest: run on every new incident insert, since you're not at real scale) that re-runs clustering and updates `entities.risk_score` based on cluster size and incident severity.

### Files touched
`backend/correlation_engine.py` (new), `backend/nlp_engine.py` (extend), `backend/main.py` (call correlation after every incident insert)

### 🔴 MODEL REQUIRED FROM YOU (optional, upgrade path)
If you want to go beyond Gemini-based entity extraction for stronger "Technical Excellence" scoring: a fine-tuned NER model (e.g. spaCy custom NER or a small fine-tuned transformer) trained on Indian phone number / UPI ID / bank account patterns in scam transcripts. **Not required to demo** — Gemini structured extraction is a legitimate fallback — but if you or a teammate can fine-tune one in the time available, this is the single highest-credibility addition to this phase.

### Definition of done
Feeding two different synthetic scam calls that mention the same phone number produces one shared entity node with two linked incidents, and a lead-time value is computed and stored.

---

## PHASE 2 — Geospatial Crime Pattern Intelligence (currently missing entirely)
**Goal:** Build the 5th sub-problem, which your app currently has zero coverage for. This is fast and highly demo-able — prioritize it early.

### Tasks
1. Backend: new endpoint `GET /api/geo/hotspots` — pulls all `incidents` with lat/lng, runs **DBSCAN** (scikit-learn) to cluster into hotspots, returns cluster centroids + density + dominant incident type per cluster.
2. Backend: new endpoint `GET /api/geo/incidents?district=&type=&since=` for raw pin data with filters.
3. Frontend: new `GeospatialView.jsx` component using **Leaflet** (lighter weight than Mapbox, no API key needed) — plot pins colored by incident type, overlay hotspot clusters as translucent circles sized by density.
4. Add a "Patrol Priority" ranked list panel next to the map — sort districts by combined hotspot density + average risk_score of linked entities. This is your direct answer to the "patrol prioritisation, resource deployment" language in the problem statement.
5. Wire into Nodal Portal sidebar as a new tab alongside Dashboard / Graph / Scanner.

### Files touched
`backend/main.py` (2 new routes), `backend/geo_engine.py` (new), `frontend/src/App.jsx` (new tab + component), `frontend/package.json` (add `leaflet`, `react-leaflet`)

### Definition of done
Map tab loads, shows seeded synthetic incidents as pins across multiple cities, hotspot clustering visibly groups dense areas, patrol priority list updates when filtered by date/type.

---

## PHASE 3 — Real Graph Intelligence (replace hardcoded fixture)
**Goal:** Your current `GraphIntelligenceView` has 8 hardcoded nodes. Replace with live data from Phase 1's correlation engine.

### Tasks
1. Backend: `GET /api/graph/full` — returns all entities + edges as nodes/links in the shape `react-force-graph-2d` expects.
2. Backend: `GET /api/graph/cluster/{cluster_id}` — returns just one suspected fraud ring, for when a user clicks into a specific cluster.
3. Frontend: rewire `GraphIntelligenceView` to fetch from these endpoints instead of the hardcoded array. Keep the existing force-directed visual style — it already looks good.
4. Add visual distinction for cluster membership (color-code nodes by their Louvain community ID) so judges can *see* the ring-detection happening, not just individual dots.
5. Node click panel: show which incidents reference this entity, its risk_score, and first_seen timestamp — this becomes the audit trail.

### Files touched
`backend/main.py` (2 new routes), `frontend/src/App.jsx` (rewire GraphIntelligenceView data source)

### Definition of done
Graph updates live when a new incident is submitted through the dashboard's "Simulate Telecom Feed" button — a new node/edge appears without a page refresh (or on next fetch/poll).

---

## PHASE 4 — Counterfeit Currency: Multi-Signal Verification
**Goal:** Right now this module is 100% Gemini Vision guessing at forgery markers with no grounded pixel-level check. This is your weakest technical link — fix it before the demo, because "how do you know Gemini isn't hallucinating this" is a very likely judge question.

### Tasks
1. Add a classical CV pre-processing pass using **OpenCV**:
   - Edge density analysis on the security-thread region (a lower-quality fake will show blurrier/inconsistent edges than a genuine note's raised print)
   - Texture variance check (Laplacian variance) as a sharpness/print-quality proxy
   - Basic color histogram comparison against reference color profiles for genuine notes (per denomination)
2. Combine: final verdict = weighted combination of Gemini Vision's forensic read + the classical CV signal, not Gemini alone. Return both scores separately in the API response so you can show "two independent signals agreed" in the demo — this is a real technical talking point.
3. Update `analyze_document()` in `nlp_engine.py` to call the new `cv_engine.py` alongside the existing Gemini call.
4. Frontend: update `CounterfeitScannerView` results panel to show both signals (e.g. "AI Forensic Read: Critical (87%)" + "Pixel-Level Verification: Anomalous edge pattern detected").

### Files touched
`backend/cv_engine.py` (new), `backend/nlp_engine.py` (extend `analyze_document`), `frontend/src/App.jsx` (update results display)

### 🔴 MODEL REQUIRED FROM YOU (recommended, high impact)
This is the single most valuable model you can personally contribute:
- **A fine-tuned image classifier (ResNet18/EfficientNet-B0 via transfer learning) trained on real vs. fake Indian currency note images**, per denomination if possible.
- Search Kaggle / GitHub for existing "Indian fake currency detection dataset" — a few small public ones exist (real/fake note image sets, often ₹500/₹2000 focused). If none are sufficient, even a small self-collected dataset (photos of a handful of genuine notes + synthetically degraded/edited fakes for contrast) fine-tuned in a Colab notebook is enough for a demo-credible model.
- **Deliverable needed from you:** an exported model file (`.h5`, `.pt`, or `.onnx`) + the class labels + the input preprocessing spec (image size, normalization). Hand this to the coding AI along with instructions — it will wire it in as a third signal alongside Gemini Vision and the OpenCV pass, turning "multi-signal verification" from two signals into three, and giving you a real trained-model artifact to point to for "Technical Excellence."
- If you cannot get this done in time, the OpenCV pass in Task 1 is a legitimate fallback — do not skip that regardless.

### Definition of done
Uploading a test note image returns a combined verdict citing at least two independent signals, not just one Gemini call.

---

## PHASE 5 — Digital Arrest Scam Detection: Precision Guardrails
**Goal:** Reduce false positives (explicitly called out in the evaluation focus: "false positive rate for citizen-facing tools must be very low") and strengthen the classifier beyond a single LLM call.

### Tasks
1. Add a **rule-based pre-filter** layer before the Gemini call: known-safe patterns (e.g. family/friend contexts, no urgency language, no request for "safe account" transfer) short-circuit to "safe" without even hitting the LLM — cheaper and reduces LLM-hallucination-driven false positives.
2. Add a **confidence floor**: only surface "critical" status to citizens if both the rule-based pre-filter flags risk indicators AND Gemini's confidence exceeds a threshold (e.g. 80%) — require agreement, not a single signal, mirroring the multi-signal approach from Phase 4.
3. Log every classification (including "safe" ones) to the `incidents` table for entity correlation — currently your `test_ai.py` shows you're only really testing the "obvious scam" case; broaden your synthetic test set to include ambiguous/borderline transcripts so you can honestly report precision/recall in your deck.
4. Build a small **eval script** (`backend/eval_classifier.py`) that runs a labeled synthetic test set (~40-50 transcripts, mix of scam/safe/ambiguous) through the pipeline and reports precision, recall, false-positive rate — you need actual numbers for the "Evaluation Focus" section of the problem statement, not just a working demo.

### Files touched
`backend/nlp_engine.py` (extend), `backend/rules_engine.py` (new), `backend/eval_classifier.py` (new)

### 🔴 MODEL REQUIRED FROM YOU (optional, upgrade path)
If time allows: a fine-tuned lightweight text classifier (e.g. DistilBERT fine-tuned on labeled scam vs. non-scam call transcripts, English + a couple of Indian languages) as a second signal alongside Gemini, following the same "multi-signal agreement" pattern as counterfeit detection. Not required — the rule-based pre-filter + confidence floor is a legitimate and much faster alternative that still gives you a defensible false-positive story.

### Definition of done
Eval script outputs a precision/recall table you can put directly into your deck. Ambiguous test transcripts don't get misclassified as confidently as before.

---

## PHASE 6 — Citizen Fraud Shield: Wire Into the Correlation Engine
**Goal:** Currently the citizen chat/mic just calls the classifier and shows a result — it doesn't feed the wider intelligence system. Fix this so a citizen report becomes part of the same graph/map/cluster data other modules use.

### Tasks
1. Every citizen chat message and mic transcript that gets classified should also go through Phase 1's entity extraction and get inserted into `incidents` with a `type: citizen_report` and rough geo-tag (can be self-reported district via a simple dropdown, or IP-based approximation — keep it simple, note the limitation in your deck).
2. If a citizen's report entity matches an existing cluster from Nodal-side data, surface this back to the citizen: "This number has been reported 4 times in the last 24 hours" — this is a strong UX moment and directly demonstrates convergence live.
3. Wire the existing "NCRB Report Drafting" modal to pull real structured data (entities extracted, incident timestamp, district) instead of being a static mock — auto-fill from the `incidents` row.
4. Language coverage: for the demo, fully test 2-3 languages end-to-end (e.g. English, Hindi, one more) rather than claiming all 13 are production-tested — be honest about this in the deck, judges respect scoped honesty over over-claiming.

### Files touched
`backend/main.py` (extend `/api/analyze` to also write citizen-flagged incidents + geo), `frontend/src/App.jsx` (citizen shield result panel, NCRB modal auto-fill)

### Definition of done
A citizen report about a phone number that already exists in a Nodal-side scam cluster surfaces a "previously reported" warning, and the same entity is visible in the Nodal graph view.

---

## PHASE 7 — Evidence Package: Real Audit Trail
**Goal:** Currently "Export Court-Admissible Package" downloads a plain text file. The evaluation criteria explicitly asks for "auditability of intelligence packages for legal admissibility" — this needs to look and behave like a real chain-of-custody artifact.

### Tasks
1. Backend: `POST /api/evidence/generate` — takes a cluster_id or list of incident_ids, compiles a structured JSON dossier (all linked entities, incidents, timestamps, confidence scores, correlation lead-time), and generates a PDF version (use `reportlab` or `weasyprint`, whichever is faster to integrate).
2. Compute a **SHA-256 hash** of the underlying JSON data and embed it in the PDF footer — frame this as a basic data-integrity/chain-of-custody mechanism (this is a cheap addition with high perceived rigor).
3. Store the generated package in `evidence_packages` table with hash + generation timestamp, so it's independently retrievable/auditable, not just a one-off download.
4. Frontend: update the export button to call this endpoint and download the real PDF instead of the current text file.

### Files touched
`backend/evidence_engine.py` (new), `backend/main.py` (new route), `frontend/src/App.jsx` (update export button)

### Definition of done
Clicking export produces a structured, hash-stamped PDF with real linked-entity data pulled from the DB, not a static text mock.

---

## PHASE 8 — Dashboard Integration & Cross-Module Live Demo Flow
**Goal:** This is where the "convergence" story becomes visible on stage. Build a scripted end-to-end sequence, not just individually working modules.

### Tasks
1. Design one scripted demo scenario spanning all modules, e.g.:
   - A synthetic scam call comes in via "Simulate Telecom Feed" → classified critical → entities extracted → correlation engine finds it matches 2 prior citizen reports from the same district → cluster risk_score spikes → node appears in Graph view → pin appears/intensifies on Geospatial hotspot map → Nodal dashboard shows an MHA alert generation button → clicking it produces the hash-stamped evidence PDF.
   - In parallel, a "citizen" on the Citizen Shield side reports the same phone number via chat and gets an instant "previously reported 3x, high risk" verdict.
2. Add a single dashboard summary panel (top of Nodal Portal) showing your headline metrics live: active fraud rings detected, average lead-time before mass victimisation, counterfeit scans today, citizen reports correlated. Judges remember dashboards with real numbers.
3. Stress-test the full flow at least 10 times before the demo — this is a multi-service, multi-step pipeline and the most likely place for live-demo failure. Have a pre-recorded fallback video ready regardless (this is also a required deliverable).

### Files touched
`frontend/src/App.jsx` (dashboard summary panel, demo trigger sequencing), possibly `backend/main.py` (a `/api/demo/trigger-scenario` convenience endpoint that fires the whole sequence in order for reliability)

### Definition of done
The full cross-module flow runs start to finish without manual page refreshes, in under 60-90 seconds, in a way that's narratable live.

---

## PHASE 9 — Deliverables: Architecture Diagram, Deck, Demo Video
**Goal:** Package everything you built into the four required deliverables.

### Tasks
1. **Architecture Diagram**: show the layered structure — data ingestion (mic/chat/image/telecom-sim) → Gemini + classical AI signals → correlation engine (entity extraction, Louvain clustering) → persistence layer → three consumer views (Nodal dashboard, Graph, Geospatial) + Citizen Shield, with the evidence export as a terminal node. Make the "multi-signal fusion" and "convergence" points visually obvious — this is your core innovation claim, so the diagram should make it undeniable at a glance.
2. **Presentation Deck**: lead with the problem statement's own numbers (1.14M complaints, ₹1,776 crore in 9 months), state your headline lead-time metric from Phase 1, show your Phase 5 precision/recall table (real numbers beat claims), be explicit and honest about what's synthetic data vs. real datasets vs. your own trained model (Phase 4) — judges respect scoped honesty.
3. **Demo Video**: record the Phase 8 scripted flow end-to-end as the primary video, with a voiceover explaining what's happening at each correlation step (this is the part that differentiates you from "we built a chatbot" submissions).
4. **Working Prototype**: make sure the whole thing runs on a fresh clone with a documented `.env` setup (get the hardcoded API key on `nlp_engine.py` line 9 out and into an environment variable now, before this becomes an embarrassing screen-share moment).

### Definition of done
All four deliverables exist as files/links ready to submit, and you've rehearsed the demo at least twice against the timer.

---

## SUMMARY: WHERE YOU MUST PERSONALLY SUPPLY SOMETHING

| Phase | What's needed from you | Required or optional |
|---|---|---|
| Phase 1 (Entity Extraction) | Fine-tuned NER model for Indian financial identifiers | Optional upgrade |
| **Phase 4 (Counterfeit CV)** | **Fine-tuned image classifier (ResNet/EfficientNet) trained on real vs. fake Indian currency images, exported as `.h5`/`.pt`/`.onnx` + labels + preprocessing spec** | **Recommended — highest impact single contribution** |
| Phase 5 (Scam Classifier) | Fine-tuned text classifier (e.g. DistilBERT) on labeled scam/non-scam transcripts | Optional upgrade |
| All phases using synthetic data | Decide/curate which public datasets (Kaggle currency images, any scam-transcript corpora) to actually source vs. synthetically generate — flag this early since dataset search takes real time | Required decision, not a model |

Everything else in this plan (persistence, correlation engine, clustering, geospatial module, evidence export, frontend wiring, demo sequencing) can be built end-to-end by the coding AI without a model handoff from you.

---

## RECOMMENDED BUILD ORDER (condensed)
1. Phase 0 — DB + seed data
2. Phase 1 — Entity extraction + correlation engine
3. Phase 2 — Geospatial module (missing sub-problem, high visual payoff, fast)
4. Phase 3 — Real graph (replace fixture)
5. Phase 4 — Counterfeit multi-signal (insert your trained model here when ready)
6. Phase 5 — Scam detection guardrails + eval numbers
7. Phase 6 — Citizen shield wiring
8. Phase 7 — Evidence package/audit trail
9. Phase 8 — Cross-module live demo flow
10. Phase 9 — Diagram, deck, video, final polish
