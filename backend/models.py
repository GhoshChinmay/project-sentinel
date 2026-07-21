from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from database import Base

def generate_uuid():
    return str(uuid.uuid4())


class Campaign(Base):
    """Represents a detected coordinated fraud campaign identified by graph analysis."""
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    name = Column(String, nullable=False)  # e.g., 'Campaign Alpha', 'Jamtara Ring 3'
    description = Column(Text, nullable=True)
    entity_count = Column(Integer, default=0)
    incident_count = Column(Integer, default=0)
    total_amount_traced = Column(Float, default=0.0)  # Total ₹ traced through this campaign
    risk_level = Column(String, default="medium")  # 'low', 'medium', 'high', 'critical'
    jurisdictions_json = Column(Text, nullable=True)  # JSON list of jurisdictions
    detected_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    entities = relationship("Entity", back_populates="campaign")


class Entity(Base):
    """Represents a unique actor: Phone Number, UPI ID, Bank Account, etc."""
    __tablename__ = "entities"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    type = Column(String, index=True) # e.g., 'phone', 'upi', 'bank_account'
    value = Column(String, unique=True, index=True) # e.g., '+919876543210'
    first_seen = Column(DateTime, default=datetime.utcnow)
    risk_score = Column(Float, default=0.0) # 0.0 to 100.0

    # --- Graph Intelligence Fields (Phase 1 Enhancement) ---
    campaign_id = Column(String, ForeignKey("campaigns.id"), nullable=True, index=True)
    centrality_score = Column(Float, default=0.0)  # Betweenness centrality (0.0 to 1.0)
    pagerank_score = Column(Float, default=0.0)  # PageRank importance (0.0 to 1.0)
    jurisdiction = Column(String, nullable=True, index=True)  # e.g., 'Maharashtra', 'Delhi NCR'

    # Relationships
    incidents = relationship("IncidentEntity", back_populates="entity")
    campaign = relationship("Campaign", back_populates="entities")

class Incident(Base):
    """Represents a single event: A call intercept, a citizen report, a scanned note."""
    __tablename__ = "incidents"

    id = Column(String, primary_key=True, index=True) # e.g., INC-1042
    type = Column(String, index=True) # 'scam_call', 'counterfeit_scan', 'citizen_report'
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String) # 'safe', 'warning', 'critical'
    confidence = Column(String)
    raw_payload_json = Column(Text) # Store the raw Groq/Gemini response
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    district = Column(String, nullable=True, index=True)

    # Relationships
    entities = relationship("IncidentEntity", back_populates="incident")

class IncidentEntity(Base):
    """Many-to-Many join table linking Incidents to Entities."""
    __tablename__ = "incident_entities"

    incident_id = Column(String, ForeignKey("incidents.id"), primary_key=True)
    entity_id = Column(String, ForeignKey("entities.id"), primary_key=True)
    role = Column(String) # e.g., 'caller', 'receiver', 'mentioned'

    # Relationships
    incident = relationship("Incident", back_populates="entities")
    entity = relationship("Entity", back_populates="incidents")

class GraphEdge(Base):
    """Defines relationships between entities for the Force Graph."""
    __tablename__ = "graph_edges"

    id = Column(Integer, primary_key=True, index=True)
    source_entity_id = Column(String, ForeignKey("entities.id"), index=True)
    target_entity_id = Column(String, ForeignKey("entities.id"), index=True)
    relationship_type = Column(String) # e.g., 'transferred_to', 'shared_device'
    weight = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # --- Graph Intelligence Fields (Phase 1 Enhancement) ---
    amount = Column(Float, nullable=True)  # Transaction amount in ₹ (for fund-flow tracing)
    direction = Column(String, default="undirected")  # 'directed' or 'undirected'
    metadata_json = Column(Text, nullable=True)  # Extra context (timestamps, references)

class EvidencePackage(Base):
    """Stores generated court-admissible dossiers."""
    __tablename__ = "evidence_packages"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    campaign_id = Column(String, ForeignKey("campaigns.id"), nullable=True, index=True)
    incident_ids_json = Column(Text) # JSON list of incident IDs included
    generated_at = Column(DateTime, default=datetime.utcnow)
    sha256_hash = Column(String)
    dossier_content = Column(Text, nullable=True)  # Full text dossier
    pdf_path = Column(String, nullable=True)

class GeoEvent(Base):
    """GCPI geo-tagged crime event from multiple source modules."""
    __tablename__ = "geo_events"

    id = Column(String, primary_key=True, default=generate_uuid, index=True)
    source_module = Column(String, index=True)    # ncrp, cctns, ficn_seizure, field_app, telecom_alert, fraud_graph
    event_type = Column(String, index=True)        # complaint, seizure, scam_call_alert, mule_node
    lat = Column(Float)
    lng = Column(Float)
    h3_cell = Column(String, index=True)           # H3 index at resolution 8
    geo_confidence = Column(String)                 # exact, tower, address
    timestamp = Column(DateTime, default=datetime.utcnow)
    severity = Column(Float, default=0.5)           # 0.0–1.0
    entity_refs_json = Column(Text, nullable=True)  # JSON list of FIR/case/entity IDs
    district = Column(String, index=True)
    pii_token = Column(String, nullable=True)       # tokenised reference only
