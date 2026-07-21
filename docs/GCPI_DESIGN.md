# Geospatial Crime Pattern Intelligence (GCPI) — Implementation Plan

This plan integrates the GCPI specification into the existing Project Sentinel codebase, scoped to **Phase 1 (MVP/hackathon-demo)** with the architecture designed to support later phases.

---

## Current State

The project has:
- **Backend**: FastAPI + SQLite/SQLAlchemy, with existing [geo_engine.py](file:///c:/Projects/project-sentinel/backend/geo_engine.py) (basic DBSCAN), [models.py](file:///c:/Projects/project-sentinel/backend/models.py) (Incident, Entity, GraphEdge tables), [correlation_engine.py](file:///c:/Projects/project-sentinel/backend/correlation_engine.py) (NetworkX GNN)
- **Frontend**: React + Vite + TailwindCSS, monolithic [App.jsx](file:///c:/Projects/project-sentinel/frontend/src/App.jsx) with Leaflet map (`GeospatialView`), ForceGraph2D graph, Acoustic Forensics lab
- **Existing Geo Tab**: Simple Leaflet map showing DBSCAN clusters + incident markers with a patrol priority sidebar

---

## What This Implementation Delivers

A **fully upgraded GCPI command centre tab** that replaces the existing basic `GeospatialView` with:

### Backend (Python)
1. **H3 Hexagonal Spatial Indexing** — every incident gets an H3 cell assignment (res 8), enabling hex-grid aggregation
2. **Getis-Ord Gi\* Hotspot Statistics** — statistically significant hot/cold cells (not just raw density)
3. **HDBSCAN Clustering** — density-adaptive clustering replacing basic DBSCAN
4. **Digital Crime Risk Index (DCRI)** — fusion score across complaint density, seizure density, scam-call density, and mule-node density per H3 cell
5. **Kulldorff Spatial Scan** — emerging cluster detection for early-warning alerts
6. **Forecast Engine** — per-cell time-series prediction using Prophet/exponential smoothing (Phase 1 fallback for ST-GNN)
7. **Expanded Geo Event Model** — common `geo_event` envelope with H3 cell, confidence level, source module, and entity refs
8. **Comprehensive API Endpoints** — H3 hexbin data, DCRI heatmap, emerging clusters, forecast, patrol allocation

### Frontend (React)  
1. **H3 Hexagonal Heatmap** — colour-coded hex grid overlay showing DCRI per cell
2. **Layer Stack Toggle** — independently toggle complaints / seizures / scam-calls / mule-network layers
3. **Time Slider** — replay historical data + show forecast horizon (−30 days to +7 days)
4. **Live Command Stats Bar** — active threats, top DCRI cells, emerging cluster count
5. **Patrol Allocation Panel** — ranked cells by DCRI × inverse patrol coverage, with "Dispatch" actions
6. **Emerging Cluster Alerts** — real-time notification of new spatial anomalies
7. **Inter-District Intelligence Sidebar** — cross-jurisdiction hotspot sharing workspace

### Database
1. **New `GeoEvent` model** — source_module, event_type, lat/lng, h3_cell, confidence, severity, entity_refs
2. **Enhanced Seed Data** — 200+ realistic geo-tagged events across Indian metros/tier-2 cities with multi-source types (NCRP, FICN seizure, scam call, mule node)

---

> [!IMPORTANT]
> **Scope Boundary**: This is Phase 1 (MVP). The full ST-GNN forecasting, Kafka/Flink streaming, PostGIS migration, federated query layer (Trino), and vector tile serving (Martin) are **architecture-documented but not implemented** — they'd require production infrastructure beyond a hackathon scope. Phase 1 uses Prophet/exponential smoothing for forecasting and SQLite for storage.

---

## Proposed Changes

### Backend — GCPI Engine

#### [NEW] [gcpi_engine.py](file:///c:/Projects/project-sentinel/backend/gcpi_engine.py)
The core GCPI analytics engine containing:
- `H3Indexer`: converts lat/lng → H3 cells at configurable resolution (default res 8, ~0.74 km²)
- `GiStarCalculator`: computes Getis-Ord Gi\* z-scores per H3 cell against k-ring neighbours
- `HDBSCANClusterer`: density-adaptive spatial clustering
- `KulldorffScanner`: spatial scan statistic for emerging cluster detection
- `DCRICalculator`: computes Digital Crime Risk Index per cell as weighted fusion of 4 signal types + forecast delta
- `ForecastEngine`: per-cell time-series forecasting (24h/72h) using exponential smoothing
- `PatrolAllocator`: ranks cells by DCRI × (1 − patrol_coverage) for deployment recommendations

---

#### [MODIFY] [models.py](file:///c:/Projects/project-sentinel/backend/models.py)
Add new `GeoEvent` SQLAlchemy model:
```python
class GeoEvent(Base):
    __tablename__ = "geo_events"
    id = Column(String, primary_key=True, default=generate_uuid)
    source_module = Column(String, index=True)  # ncrp, cctns, ficn_seizure, field_app, telecom_alert, fraud_graph
    event_type = Column(String, index=True)      # complaint, seizure, scam_call_alert, mule_node
    lat = Column(Float)
    lng = Column(Float)
    h3_cell = Column(String, index=True)         # H3 index at resolution 8
    geo_confidence = Column(String)               # exact, tower, address
    timestamp = Column(DateTime, default=datetime.utcnow)
    severity = Column(Float, default=0.5)         # 0.0–1.0
    entity_refs_json = Column(Text)               # JSON list of FIR/case/entity IDs
    district = Column(String, index=True)
    pii_token = Column(String, nullable=True)     # tokenised reference only
```

---

#### [MODIFY] [geo_engine.py](file:///c:/Projects/project-sentinel/backend/geo_engine.py)
**Replace** the existing basic DBSCAN logic with calls into `gcpi_engine.py`. The existing functions (`get_geo_incidents`, `get_hotspots`) are preserved for backward compatibility but enhanced. New functions added:
- `get_h3_hexbins(db, days, resolution)` → aggregated H3 cells with DCRI scores
- `get_emerging_clusters(db, days)` → Kulldorff scan results
- `get_forecast(db, cell_id, horizon_hours)` → per-cell forecast
- `get_patrol_allocation(db, top_n)` → ranked patrol deployment recommendations

---

#### [MODIFY] [main.py](file:///c:/Projects/project-sentinel/backend/main.py)
Add new API routes under `/api/gcpi/`:
- `GET /api/gcpi/hexgrid` — H3 hexbin grid with DCRI scores, layer-filtered
- `GET /api/gcpi/hotspots` — Gi\* statistically significant hotspots
- `GET /api/gcpi/emerging` — Kulldorff emerging cluster alerts
- `GET /api/gcpi/forecast/{h3_cell}` — per-cell forecast data
- `GET /api/gcpi/patrol` — ranked patrol allocation recommendations
- `GET /api/gcpi/stats` — aggregate GCPI dashboard stats
- `WebSocket /ws/gcpi-live` — push live updates (emerging alerts, DCRI changes) to command centre

---

#### [MODIFY] [seed_data.py](file:///c:/Projects/project-sentinel/backend/seed_data.py)
Add a `seed_geo_events()` function that creates 200+ realistic `GeoEvent` records across:
- 15 Indian cities (Jamtara, Mewat, Mumbai, Delhi, Bengaluru, Hyderabad, Chennai, Kolkata, Pune, Ahmedabad, Lucknow, Jaipur, Chandigarh, Kochi, Indore)
- 4 event types distributed realistically (more complaints in metros, more mule nodes in Jamtara/Mewat)
- Temporal spread over 30 days with realistic burst patterns (salary-day spikes, weekend dips)

---

#### [MODIFY] [requirements.txt](file:///c:/Projects/project-sentinel/backend/requirements.txt)
Add:
```
h3
hdbscan
scipy
```
(`scipy` is already a transitive dep but we pin it; `h3` is the Uber H3 Python bindings; `hdbscan` for density-adaptive clustering)

---

### Frontend — GCPI Command Centre

#### [MODIFY] [App.jsx](file:///c:/Projects/project-sentinel/frontend/src/App.jsx)
**Replace** the existing `GeospatialView` component (lines 810–859) with a full-featured GCPI Command Centre component:

1. **Header Bar**: "GCPI COMMAND CENTRE" with live stats (active events, emerging clusters, top DCRI district)
2. **Map Area**: Leaflet map with:
   - H3 hexagonal overlay (polygon layer, colour-coded by DCRI — green → yellow → red)
   - Toggleable incident pin layers (complaints, seizures, scam calls, mule nodes) with distinct icons/colors
   - Hotspot circles from Gi\* analysis
   - Emerging cluster pulse markers (animated)
3. **Left Control Panel**:
   - Layer toggle checkboxes (Complaints, FICN Seizures, Scam Calls, Mule Network)
   - Time slider (−30 days to +7 days forecast)
   - Resolution picker (H3 res 7/8/9)
4. **Right Intelligence Panel**:
   - Patrol Priority ranked list (top-N cells by DCRI)
   - Emerging Cluster alerts with "Investigate" button
   - Cross-District Intelligence cards (hotspots spanning multiple districts)
5. **Bottom Forecast Strip**: Mini sparkline per top-5 cell showing 7-day trend + forecast

---

#### [MODIFY] [package.json](file:///c:/Projects/project-sentinel/frontend/package.json)
Add dependency:
```
"h3-js": "^4.1.0"
```
(Client-side H3 → polygon boundary conversion for rendering hexagons on Leaflet)

---

## Verification Plan

### Automated Tests
```bash
# 1. Seed the GCPI data
cd c:\Projects\project-sentinel\backend
python -c "from seed_data import seed_geo_events; seed_geo_events()"

# 2. Start backend and verify new endpoints
uvicorn main:app --reload
# Then test:
curl http://127.0.0.1:8000/api/gcpi/hexgrid
curl http://127.0.0.1:8000/api/gcpi/hotspots
curl http://127.0.0.1:8000/api/gcpi/emerging
curl http://127.0.0.1:8000/api/gcpi/patrol
curl http://127.0.0.1:8000/api/gcpi/stats
```

### Manual Verification
- Navigate to the "Tactical Map" tab in the Nodal Portal
- Verify H3 hexagonal grid renders over India map with colour-coded DCRI
- Toggle individual layers on/off
- Use time slider to see historical data and forecast
- Check patrol allocation panel shows ranked cells
- Confirm emerging cluster alerts appear for high-density areas

---

## Open Questions

> [!IMPORTANT]
> **Sidebar Navigation**: The GCPI view will replace the existing "Tactical Map" tab. Should I keep the old simple view accessible via a toggle, or fully replace it?

> [!NOTE]  
> **H3 Dependency**: The `h3` Python package requires C compilation. If this fails on your Windows setup, I'll fall back to a pure-Python hex grid approximation. The `h3-js` npm package is pure JS and should install cleanly.
