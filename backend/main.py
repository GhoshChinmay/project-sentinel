from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import json
import uuid
import io
import base64
import numpy as np
import scipy.io.wavfile as wavfile

# --- AI ENGINES ---
from nlp_engine import analyzer                       # Feature 1: Digital Arrest NLP (Groq)
from vision_engine import vision_analyzer             # Feature 2: Counterfeit Currency (OpenRouter)
from audio_engine import audio_analyzer               # Feature 1: Audio deepfake detection
from database import engine, get_db
from models import Base, Incident, Entity, GraphEdge, Campaign, GeoEvent
from correlation_engine import correlate_and_cluster
from geo_engine import (
    get_geo_incidents, get_hotspots,
    get_h3_hexbins, get_gcpi_hotspots, get_emerging_clusters,
    get_forecast, get_patrol_allocation, get_gcpi_stats, get_full_gcpi,
    log_geo_event, get_geo_events, pick_random_district
)
# Feature 3: Graph Intelligence & Evidence Generation
from graph_engine import run_full_analysis, get_campaigns, get_entity_deep_dive
from evidence_engine import generate_evidence_package
from gcpi_intel import generate_intel_package

# Create database tables if they don't exist
Base.metadata.create_all(bind=engine)

# Initialize the backend app
app = FastAPI(title="Project Sentinel API")

# Allow our React frontend to talk to this Python backend without security blocks (CORS).
# Wildcard origin (no credentials are used by either portal), which keeps the localhost
# demo, the Vite proxy, and LAN access all working.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REQUEST MODELS ---
class TranscriptRequest(BaseModel):
    transcript: str
    caller_id: str = "Unknown"

class DocumentRequest(BaseModel):
    image_base64: str

class AudioForensicRequest(BaseModel):
    audio_base64: str

class AnalyzeRequest(BaseModel):
    """Optional body for graph analysis trigger."""
    force: bool = False

class EvidenceRequest(BaseModel):
    campaign_id: Optional[str] = None

# Our basic health check route
@app.get("/")
def read_root():
    return {
        "status": "Sentinel API Online",
        "version": "4.0",
        "architecture": "Unified — Split-Stream NLP/Audio + Counterfeit Vision + Graph Intelligence + GCPI"
    }


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE 1 — DIGITAL ARREST SCAM DETECTION
# ═══════════════════════════════════════════════════════════════════════════

# --- SPLIT-STREAM LANE 1: TEXT SEMANTICS (For the Live Microphone) ---
@app.post("/api/analyze")
def analyze_call(request: TranscriptRequest, db: Session = Depends(get_db)):
    # 1. Pass the incoming text to our AI engine
    result = analyzer.analyze_transcript(request.transcript)

    # 2. Write to Database using a secure UUID to prevent IntegrityError crashes
    incident_id = f"INC-{uuid.uuid4().hex[:6].upper()}"

    # Pick a random district for realistic geo spread across India
    district, lat, lng = pick_random_district()

    new_incident = Incident(
        id=incident_id,
        type="scam_call",
        status=result.get("status", "safe"),
        confidence=result.get("confidence", "0%"),
        raw_payload_json=json.dumps(result),
        district=district,
        lat=lat,
        lng=lng
    )
    db.add(new_incident)
    db.commit()

    # 3. BRIDGE TO GCPI MAP — log a GeoEvent so this shows up on the command centre
    status = result.get("status", "safe")
    severity = 0.9 if status == "critical" else 0.6 if status == "warning" else 0.3
    try:
        log_geo_event(db, "ncrp", "scam_call_alert", lat, lng, severity, district,
                      entity_refs=[incident_id])
    except Exception:
        pass  # Never break ingestion

    # 4. EXTRACTION & CORRELATION: run the unified Graph engine (lead-time + GNN metrics)
    extracted = analyzer.extract_entities(request.transcript)
    lead_time_results = correlate_and_cluster(db, incident_id, extracted, incident_district=district)

    # Mix graph analytics back into the response payload for the frontend
    extended_analysis = {**result, "lead_time": lead_time_results}
    new_incident.raw_payload_json = json.dumps(extended_analysis)
    db.commit()

    return {
        "success": True,
        "caller_id": request.caller_id,
        "incident_id": incident_id,
        "analysis": extended_analysis
    }


# --- SPLIT-STREAM LANE 2: ACOUSTIC FORENSICS (audio deepfake) ---
@app.post("/api/analyze-audio")
def analyze_audio(request: AudioForensicRequest, db: Session = Depends(get_db)):
    try:
        wav_bytes = base64.b64decode(request.audio_base64)
        result = audio_analyzer.analyze_audio_wave(wav_bytes)

        is_deepfake = result.get("is_synthetic_voice", False)

        # Log to Database using secure UUID
        incident_id = f"AUD-{uuid.uuid4().hex[:6].upper()}"
        district, lat, lng = pick_random_district()
        new_incident = Incident(
            id=incident_id,
            type="audio_deepfake_scan",
            status="critical" if is_deepfake else "safe",
            confidence=f"{result.get('deepfake_probability', 0)}%",
            raw_payload_json=json.dumps(result, default=str),
            district=district,
            lat=lat,
            lng=lng
        )
        db.add(new_incident)
        db.commit()

        # BRIDGE TO GCPI MAP — deepfake detections appear as scam_call_alert
        if is_deepfake:
            try:
                log_geo_event(db, "telecom_alert", "scam_call_alert", lat, lng, 0.85, district,
                              entity_refs=[incident_id])
            except Exception:
                pass

        return {
            "success": True,
            "incident_id": incident_id,
            "deepfake_alert": is_deepfake,
            "analysis": result
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- LIVE AUDIO DEEPFAKE DETECTION (WebSocket) ---
@app.websocket("/ws/live-audio")
async def websocket_live_audio(websocket: WebSocket):
    """Real-time deepfake detection over WebSocket.
    Accepts binary WAV chunks (~4 seconds each) from the frontend,
    runs the tri-layer ensemble, and pushes results back instantly."""
    await websocket.accept()
    print("[WS] Live Audio WebSocket connected.")
    try:
        while True:
            # Receive binary audio data (raw WAV bytes)
            wav_bytes = await websocket.receive_bytes()

            if len(wav_bytes) < 100:
                continue  # Skip empty/noise chunks

            # Run the full tri-layer ensemble
            result = audio_analyzer.analyze_audio_chunk_fast(wav_bytes)

            is_deepfake = result.get("is_synthetic_voice", False)

            # Send result back to client as JSON
            await websocket.send_json({
                "deepfake_alert": is_deepfake,
                "deepfake_probability": result.get("deepfake_probability", 0),
                "verdict": result.get("audio_signal", "Unknown"),
                "layers_flagged": result.get("layers_flagged", 0),
                "layers_total": result.get("layers_total", 0),
                "layer_wav2vec": {
                    "is_deepfake": result.get("layer_wav2vec", {}).get("is_deepfake", False),
                    "confidence": result.get("layer_wav2vec", {}).get("confidence", 0),
                    "detail": result.get("layer_wav2vec", {}).get("detail", ""),
                },
                "layer_biomechanical": {
                    "is_deepfake": result.get("layer_biomechanical", {}).get("is_deepfake", False),
                    "confidence": result.get("layer_biomechanical", {}).get("confidence", 0),
                    "glottal_jitter": result.get("layer_biomechanical", {}).get("glottal_jitter", 0),
                    "vocal_shimmer": result.get("layer_biomechanical", {}).get("vocal_shimmer", 0),
                    "detail": result.get("layer_biomechanical", {}).get("detail", ""),
                },
                "layer_spectral": {
                    "is_deepfake": result.get("layer_spectral", {}).get("is_deepfake", False),
                    "confidence": result.get("layer_spectral", {}).get("confidence", 0),
                    "spectral_flatness": result.get("layer_spectral", {}).get("spectral_flatness", 0),
                    "detail": result.get("layer_spectral", {}).get("detail", ""),
                },
            })
    except WebSocketDisconnect:
        print("[WS] Live Audio WebSocket disconnected.")
    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except Exception:
            pass


# --- DEMO AUDIO GENERATOR FOR FRONTEND ---
@app.get("/api/demo-audio/{audio_type}")
def get_demo_audio(audio_type: str):
    sample_rate = 44100
    t = np.linspace(0, 2, int(sample_rate * 2), endpoint=False)

    if audio_type == "fake":
        signal = 0.5 * np.sin(2 * np.pi * 440 * t)
        vocoder_hiss = np.random.normal(0, 0.02, signal.shape)
        final_signal = signal + vocoder_hiss
    else:
        f0 = 440 + 5 * np.sin(2 * np.pi * 5 * t)
        signal = (0.5 * np.sin(2 * np.pi * f0 * t) + 0.2 * np.sin(2 * np.pi * f0 * 2 * t) + 0.1 * np.sin(2 * np.pi * f0 * 3 * t))
        hf_peak = 0.1 * np.sin(2 * np.pi * 18000 * t)
        room_noise = np.random.normal(0, 0.01, signal.shape)
        final_signal = signal + hf_peak + room_noise

    byte_io = io.BytesIO()
    wavfile.write(byte_io, sample_rate, final_signal.astype(np.float32))
    wav_bytes = byte_io.getvalue()

    return {"success": True, "audio_base64": base64.b64encode(wav_bytes).decode('utf-8')}


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE 2 — COUNTERFEIT CURRENCY (Vision AI)
# ═══════════════════════════════════════════════════════════════════════════
@app.post("/api/scan-document")
def scan_document(request: DocumentRequest, db: Session = Depends(get_db)):
    # Pass the base64 image data to the TRI-FACTOR vision AI engine
    result = vision_analyzer.analyze_document(request.image_base64)

    incident_id = f"SCAN-{uuid.uuid4().hex[:6].upper()}"
    district, lat, lng = pick_random_district()
    new_incident = Incident(
        id=incident_id,
        type="counterfeit_scan",
        status=result.get("status", "safe"),
        confidence=result.get("confidence", "0%"),
        raw_payload_json=json.dumps(result),
        district=district,
        lat=lat,
        lng=lng
    )
    db.add(new_incident)
    db.commit()

    # BRIDGE TO GCPI MAP — critical counterfeit scans appear as seizure points
    scan_status = result.get("status", "safe")
    if scan_status == "critical":
        try:
            log_geo_event(db, "ficn_seizure", "seizure", lat, lng, 0.9, district,
                          entity_refs=[incident_id])
        except Exception:
            pass

    return {
        "success": True,
        "incident_id": incident_id,
        "analysis": result
    }


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE 4 — GEOSPATIAL CRIME PATTERN INTELLIGENCE (GCPI)
# ═══════════════════════════════════════════════════════════════════════════

# --- LEGACY GEO INTELLIGENCE BRIDGE ---
@app.get("/api/geo/incidents")
def get_incidents_route(district: Optional[str] = None, incident_type: Optional[str] = None, days: int = 7, db: Session = Depends(get_db)):
    incidents = get_geo_incidents(db, district, incident_type, days)
    return {"success": True, "data": incidents}

@app.get("/api/geo/hotspots")
def get_hotspots_route(days: int = 7, db: Session = Depends(get_db)):
    hotspots = get_hotspots(db, days)
    return {"success": True, "data": hotspots}


# --- GCPI COMMAND CENTRE API ---
@app.get("/api/gcpi/hexgrid")
def gcpi_hexgrid(days: int = 30, resolution: int = 8, layers: Optional[str] = None, db: Session = Depends(get_db)):
    """H3 hexbin grid with DCRI scores. Optional layer filter: comma-separated event types."""
    event_types = layers.split(",") if layers else None
    data = get_h3_hexbins(db, days, resolution, event_types)
    return {"success": True, "data": data}

@app.get("/api/gcpi/hotspots")
def gcpi_hotspots(days: int = 30, db: Session = Depends(get_db)):
    """Gi*-based statistically significant hotspots."""
    data = get_gcpi_hotspots(db, days)
    return {"success": True, "data": data}

@app.get("/api/gcpi/emerging")
def gcpi_emerging(days: int = 30, db: Session = Depends(get_db)):
    """Kulldorff spatial scan emerging cluster alerts."""
    data = get_emerging_clusters(db, days)
    return {"success": True, "data": data}

@app.get("/api/gcpi/forecast/{h3_cell}")
def gcpi_forecast(h3_cell: str, days: int = 30, horizon: int = 168, db: Session = Depends(get_db)):
    """Per-cell time-series forecast."""
    data = get_forecast(db, h3_cell, days, horizon)
    return {"success": True, "data": data}

@app.get("/api/gcpi/patrol")
def gcpi_patrol(days: int = 30, top_n: int = 10, db: Session = Depends(get_db)):
    """Ranked patrol deployment recommendations."""
    data = get_patrol_allocation(db, days, top_n)
    return {"success": True, "data": data}

@app.get("/api/gcpi/stats")
def gcpi_stats(days: int = 30, db: Session = Depends(get_db)):
    """Aggregate GCPI dashboard statistics."""
    data = get_gcpi_stats(db, days)
    return {"success": True, "data": data}

@app.get("/api/gcpi/full")
def gcpi_full(days: int = 30, resolution: int = 8, layers: Optional[str] = None, db: Session = Depends(get_db)):
    """Full GCPI pipeline — single request loads entire command centre."""
    event_types = layers.split(",") if layers else None
    data = get_full_gcpi(db, days, resolution, event_types)
    return {"success": True, "data": data}


@app.get("/api/gcpi/events")
def gcpi_events(days: int = 30, layers: Optional[str] = None, db: Session = Depends(get_db)):
    """Raw GeoEvent points for point-marker rendering on the command centre map."""
    event_types = layers.split(",") if layers else None
    data = get_geo_events(db, days, event_types)
    return {"success": True, "data": data}


@app.get("/api/gcpi/intel-package/{district}")
def gcpi_intel_package(district: str, days: int = 30, db: Session = Depends(get_db)):
    """Generates a shareable inter-district intelligence brief with SHA-256 hash."""
    result = generate_intel_package(db, district, days)
    if "error" in result:
        return {"success": False, "error": result["error"]}
    return {"success": True, "data": result}


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE 3 — FRAUD NETWORK GRAPH INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════

# Campaign color palette for graph visualization
CAMPAIGN_COLORS = [
    '#E53E3E', '#DD6B20', '#D69E2E', '#38A169', '#3182CE',
    '#805AD5', '#D53F8C', '#E53E3E', '#2B6CB0', '#C05621',
    '#2F855A', '#6B46C1', '#B83280', '#C53030', '#2C7A7B'
]

@app.get("/api/graph/full")
def get_full_graph(db: Session = Depends(get_db)):
    """Pulls all entities and relationships to render the live network graph.
    Enhanced with campaign clustering, centrality scores, and directed edge info."""
    entities = db.query(Entity).all()
    edges = db.query(GraphEdge).all()
    campaigns = db.query(Campaign).all()

    # Build campaign_id -> color + name lookup
    campaign_lookup = {}
    for idx, c in enumerate(campaigns):
        campaign_lookup[c.id] = {
            "color": CAMPAIGN_COLORS[idx % len(CAMPAIGN_COLORS)],
            "name": c.name,
            "risk_level": c.risk_level
        }

    nodes = []
    for e in entities:
        # Use campaign color if assigned, otherwise fall back to entity-type color
        if e.campaign_id and e.campaign_id in campaign_lookup:
            color = campaign_lookup[e.campaign_id]["color"]
            campaign_name = campaign_lookup[e.campaign_id]["name"]
        else:
            campaign_name = None
            # Fallback to entity type colors
            color = '#15284B'  # Default Dark Blue
            if e.type == 'phone': color = '#D32F2F'  # Critical Red
            elif e.type == 'upi': color = '#F59E0B'  # Warning Orange
            elif e.type == 'bank_account': color = '#138808'  # Safe Green
            elif e.type == 'person': color = '#8B5CF6'  # Purple
            elif e.type == 'institution': color = '#3B82F6'  # Blue

        # Scale node size: high centrality = bigger node (ringleader effect)
        base_size = max(5, e.risk_score / 10)
        centrality_boost = e.centrality_score * 15  # Boost for high-centrality nodes
        node_size = base_size + centrality_boost

        nodes.append({
            "id": e.id,
            "name": e.value,
            "type": e.type.replace('_', ' ').upper(),
            "score": e.risk_score,
            "val": node_size,
            "color": color,
            # Phase 2 enrichments
            "centrality": round(e.centrality_score, 4),
            "pagerank": round(e.pagerank_score, 4),
            "campaign_id": e.campaign_id,
            "campaign_name": campaign_name,
            "jurisdiction": e.jurisdiction
        })

    links = []
    for edge in edges:
        links.append({
            "source": edge.source_entity_id,
            "target": edge.target_entity_id,
            "label": edge.relationship_type.replace('_', ' ').title(),
            # Phase 2 enrichments
            "amount": edge.amount,
            "direction": edge.direction or "undirected",
            "relationship_type": edge.relationship_type
        })

    return {"success": True, "data": {"nodes": nodes, "links": links, "campaigns": [
        {
            "id": c.id,
            "name": c.name,
            "entity_count": c.entity_count,
            "incident_count": c.incident_count,
            "total_amount_traced": c.total_amount_traced,
            "risk_level": c.risk_level,
            "jurisdictions": json.loads(c.jurisdictions_json) if c.jurisdictions_json else []
        } for c in campaigns
    ]}}


@app.get("/api/graph/campaigns")
def get_campaigns_route(db: Session = Depends(get_db)):
    """Returns all detected fraud campaigns with summary statistics."""
    campaigns_list = get_campaigns(db)
    return {"success": True, "data": campaigns_list}


@app.get("/api/graph/entity/{entity_id}")
def get_entity_detail(entity_id: str, db: Session = Depends(get_db)):
    """Deep-dive into a single entity: linked incidents, neighbors, fund flows."""
    detail = get_entity_deep_dive(db, entity_id)
    if "error" in detail:
        return {"success": False, "error": detail["error"]}
    return {"success": True, "data": detail}


@app.post("/api/graph/analyze")
def trigger_graph_analysis(db: Session = Depends(get_db)):
    """Triggers on-demand full graph re-analysis (Louvain + PageRank + centrality)."""
    result = run_full_analysis(db)
    return {"success": True, "data": result}


@app.post("/api/evidence/generate")
def generate_evidence(request: EvidenceRequest, db: Session = Depends(get_db)):
    """Generates a SHA-256 hashed court-admissible evidence dossier."""
    result = generate_evidence_package(db, campaign_id=request.campaign_id)
    if "error" in result:
        return {"success": False, "error": result["error"]}
    return {"success": True, "data": result}
