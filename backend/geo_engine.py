"""
Geo Engine — Enhanced with GCPI integration.
Original DBSCAN-based functions preserved for backward compatibility.
New GCPI-powered functions added for the advanced command centre.
"""
# Defer annotation evaluation so PEP 604 unions (e.g. `str | None`) parse on
# Python 3.9 (this machine's interpreter). No runtime behaviour change.
from __future__ import annotations

import random
import json
import numpy as np
from sklearn.cluster import DBSCAN
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from models import Incident, GeoEvent
from gcpi_engine import GCPIPipeline, H3Indexer
from seed_data import CITIES

# --- District centroid lookup built from the seed data CITIES table ---
DISTRICT_CENTROIDS = {c["district"]: (c["lat"], c["lng"]) for c in CITIES}
_h3_indexer = H3Indexer(resolution=8)


# ============================================================================
# ORIGINAL FUNCTIONS (Preserved for backward-compat / legacy view toggle)
# ============================================================================

def get_geo_incidents(db: Session, district: str | None = None, incident_type: str | None = None, days_since: int = 7):
    """Pulls raw geographical pins for the map (legacy)."""
    query = db.query(Incident).filter(Incident.lat.isnot(None), Incident.lng.isnot(None))
    
    if district:
        query = query.filter(Incident.district == district)
    if incident_type:
        query = query.filter(Incident.type == incident_type)
    if days_since:
        cutoff = datetime.utcnow() - timedelta(days=days_since)
        query = query.filter(Incident.timestamp >= cutoff)
        
    incidents = query.all()
    return [
        {
            "id": inc.id,
            "type": inc.type,
            "status": inc.status,
            "lat": inc.lat,
            "lng": inc.lng,
            "district": inc.district,
            "timestamp": inc.timestamp.isoformat()
        } for inc in incidents
    ]

def get_hotspots(db: Session, days_since: int = 7):
    """Uses DBSCAN to cluster nearby incidents into Patrol Priority Hotspots (legacy)."""
    cutoff = datetime.utcnow() - timedelta(days=days_since)
    incidents = db.query(Incident).filter(
        Incident.lat.isnot(None), 
        Incident.lng.isnot(None),
        Incident.timestamp >= cutoff
    ).all()
    
    if not incidents:
        return []

    # Extract coordinates into a NumPy array
    coords = np.array([[inc.lat, inc.lng] for inc in incidents])
    
    # DBSCAN clustering: eps 0.05 is roughly 5km radius in coordinate degrees
    # min_samples=2 means at least 2 incidents close together form a hotspot
    dbscan = DBSCAN(eps=0.05, min_samples=2).fit(coords)
    
    clusters = {}
    for idx, label in enumerate(dbscan.labels_):
        if label == -1: # -1 means noise (isolated incident)
            continue
            
        inc = incidents[idx]
        if label not in clusters:
            clusters[label] = {
                "id": int(label),
                "lats": [],
                "lngs": [],
                "incidents": [],
                "district": inc.district
            }
        clusters[label]["lats"].append(inc.lat)
        clusters[label]["lngs"].append(inc.lng)
        clusters[label]["incidents"].append(inc.type)
        
    # Format the hotspots for the frontend UI
    hotspots = []
    for label, data in clusters.items():
        hotspots.append({
            "cluster_id": data["id"],
            "center_lat": sum(data["lats"]) / len(data["lats"]),
            "center_lng": sum(data["lngs"]) / len(data["lngs"]),
            "density": len(data["lats"]),
            "district": data["district"],
            "dominant_type": max(set(data["incidents"]), key=data["incidents"].count)
        })
        
    # Return sorted by highest density first (Highest Patrol Priority)
    return sorted(hotspots, key=lambda x: x["density"], reverse=True)


# ============================================================================
# LIVE INCIDENT → MAP BRIDGE
# ============================================================================

def log_geo_event(
    db: Session,
    source_module: str,
    event_type: str,
    lat: float,
    lng: float,
    severity: float,
    district: str,
    entity_refs: list | None = None,
) -> str | None:
    """
    Bridge function: inserts a GeoEvent row so that incidents from Features 1-3
    appear on the GCPI command-centre map.  Wrapped in try/except internally so
    it never breaks the calling ingestion route.

    Returns the GeoEvent id on success, None on failure.
    """
    try:
        # Add small scatter so points don't stack on exact same pixel
        scatter = 0.12
        lat = round(lat + random.uniform(-scatter, scatter), 6)
        lng = round(lng + random.uniform(-scatter, scatter), 6)

        # Compute H3 cell
        h3_cell = _h3_indexer.latlng_to_cell(lat, lng)

        geo_event = GeoEvent(
            source_module=source_module,
            event_type=event_type,
            lat=lat,
            lng=lng,
            h3_cell=h3_cell,
            geo_confidence="exact",
            severity=round(min(1.0, max(0.0, severity)), 2),
            entity_refs_json=json.dumps(entity_refs or []),
            district=district,
        )
        db.add(geo_event)
        db.commit()
        db.refresh(geo_event)
        return geo_event.id
    except Exception as e:
        print(f"[geo_engine] log_geo_event failed (non-fatal): {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None


def pick_random_district() -> tuple:
    """Pick a random district + lat/lng from the CITIES centroid table."""
    city = random.choice(CITIES)
    return city["district"], city["lat"], city["lng"]


def get_geo_events(db: Session, days: int = 30, event_types: list | None = None) -> list:
    """
    Public wrapper around _fetch_geo_events that serialises timestamps to ISO
    strings — used by the /api/gcpi/events endpoint for point-marker rendering.
    """
    raw = _fetch_geo_events(db, days, event_types)
    for ev in raw:
        ts = ev.get("timestamp")
        if ts and not isinstance(ts, str):
            ev["timestamp"] = ts.isoformat()
    return raw


# ============================================================================
# GCPI-POWERED FUNCTIONS (New)
# ============================================================================

def _fetch_geo_events(db: Session, days: int = 30, event_types: list | None = None) -> list:
    """Fetch GeoEvent records from DB and return as dicts for the GCPI pipeline."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = db.query(GeoEvent).filter(
        GeoEvent.lat.isnot(None),
        GeoEvent.lng.isnot(None),
        GeoEvent.timestamp >= cutoff,
    )
    if event_types:
        query = query.filter(GeoEvent.event_type.in_(event_types))
    
    events = query.all()
    return [
        {
            "id": ev.id,
            "source_module": ev.source_module,
            "event_type": ev.event_type,
            "lat": ev.lat,
            "lng": ev.lng,
            "h3_cell": ev.h3_cell,
            "timestamp": ev.timestamp,
            "severity": ev.severity,
            "district": ev.district,
            "entity_refs_json": ev.entity_refs_json,
            "geo_confidence": ev.geo_confidence,
        }
        for ev in events
    ]


# Singleton pipeline instance (created once, reused)
_pipeline = GCPIPipeline(resolution=8)


def get_h3_hexbins(db: Session, days: int = 30, resolution: int = 8, event_types: list | None = None):
    """H3 hexbin grid with DCRI scores and Gi* hotspot data."""
    global _pipeline
    if _pipeline.resolution != resolution:
        _pipeline = GCPIPipeline(resolution=resolution)
    
    events = _fetch_geo_events(db, days, event_types)
    result = _pipeline.run_full_pipeline(events, days)
    return result["hexgrid"]


def get_gcpi_hotspots(db: Session, days: int = 30):
    """Gi*-based statistically significant hotspots."""
    events = _fetch_geo_events(db, days)
    result = _pipeline.run_full_pipeline(events, days)
    return result["hotspots"]


def get_emerging_clusters(db: Session, days: int = 30):
    """Kulldorff spatial scan for emerging cluster detection."""
    events = _fetch_geo_events(db, days)
    result = _pipeline.run_full_pipeline(events, days)
    return result["emerging_clusters"]


def get_forecast(db: Session, cell_id: str, days: int = 30, horizon_hours: int = 168):
    """Per-cell forecast data."""
    events = _fetch_geo_events(db, days)
    result = _pipeline.run_full_pipeline(events, days)
    if cell_id in result["forecast"]:
        return result["forecast"][cell_id]
    return {"historical": [], "forecast": [], "trend_delta": 0}


def get_patrol_allocation(db: Session, days: int = 30, top_n: int = 10):
    """Ranked patrol deployment recommendations."""
    events = _fetch_geo_events(db, days)
    result = _pipeline.run_full_pipeline(events, days)
    return result["patrol_allocation"]


def get_gcpi_stats(db: Session, days: int = 30):
    """Aggregate GCPI dashboard statistics."""
    events = _fetch_geo_events(db, days)
    result = _pipeline.run_full_pipeline(events, days)
    return result["stats"]


def get_full_gcpi(db: Session, days: int = 30, resolution: int = 8, event_types: list | None = None):
    """Full GCPI pipeline result — used for the comprehensive command centre load."""
    global _pipeline
    if _pipeline.resolution != resolution:
        _pipeline = GCPIPipeline(resolution=resolution)
    
    events = _fetch_geo_events(db, days, event_types)
    return _pipeline.run_full_pipeline(events, days)