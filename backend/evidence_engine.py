"""
Evidence Engine — Project Sentinel Phase 3
============================================
Generates SHA-256 hashed, court-admissible evidence dossiers on the backend.
Replaces the frontend-only text export with a real cryptographic evidence package.

Uses only hashlib, json, datetime (standard library).
"""

import hashlib
import json
from datetime import datetime
from sqlalchemy.orm import Session
from models import Entity, Incident, IncidentEntity, GraphEdge, Campaign, EvidencePackage


def generate_evidence_package(db: Session, campaign_id: str = None) -> dict:
    """
    Generates a comprehensive court-admissible evidence dossier.

    If campaign_id is provided, scopes the dossier to that campaign.
    Otherwise, generates a full-network intelligence report.

    Returns: { "package_id": "...", "sha256": "...", "content": "...", "generated_at": "..." }
    """
    timestamp = datetime.utcnow()
    timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

    # Gather data based on scope
    if campaign_id:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            return {"error": "Campaign not found", "campaign_id": campaign_id}

        entities = db.query(Entity).filter(Entity.campaign_id == campaign_id).all()
        entity_ids = [e.id for e in entities]

        # Get all incidents linked to campaign entities
        incident_ids = set()
        for eid in entity_ids:
            links = db.query(IncidentEntity).filter(IncidentEntity.entity_id == eid).all()
            for link in links:
                incident_ids.add(link.incident_id)

        incidents = db.query(Incident).filter(Incident.id.in_(list(incident_ids))).all()

        # Get edges within campaign
        edges = db.query(GraphEdge).filter(
            GraphEdge.source_entity_id.in_(entity_ids),
            GraphEdge.target_entity_id.in_(entity_ids)
        ).all()

        scope_name = campaign.name
        scope_risk = campaign.risk_level.upper()
        jurisdictions = json.loads(campaign.jurisdictions_json) if campaign.jurisdictions_json else []
    else:
        entities = db.query(Entity).all()
        incidents = db.query(Incident).all()
        edges = db.query(GraphEdge).all()
        entity_ids = [e.id for e in entities]
        scope_name = "FULL NETWORK INTELLIGENCE REPORT"
        scope_risk = "COMPREHENSIVE"
        jurisdictions = list(set(e.jurisdiction for e in entities if e.jurisdiction))
        campaign = None

    # ─── BUILD THE DOSSIER ─────────────────────────────────────────
    lines = []
    lines.append("=" * 72)
    lines.append("GOVERNMENT OF INDIA — MINISTRY OF HOME AFFAIRS (I4C)")
    lines.append("INDIAN CYBER CRIME COORDINATION CENTRE")
    lines.append("COURT-ADMISSIBLE CYBER INTELLIGENCE DOSSIER")
    lines.append("=" * 72)
    lines.append(f"GENERATED:        {timestamp_str}")
    lines.append(f"AUTHORIZATION:    NODAL OFFICER (AUTOMATED SYSTEM)")
    lines.append(f"TARGET CLUSTER:   {scope_name}")
    lines.append(f"THREAT LEVEL:     {scope_risk}")
    lines.append(f"JURISDICTIONS:    {', '.join(jurisdictions) if jurisdictions else 'Pan-India'}")
    lines.append("-" * 72)
    lines.append("")

    # ─── EXECUTIVE SUMMARY ─────────────────────────────────────────
    lines.append("SECTION 1: EXECUTIVE SUMMARY")
    lines.append("-" * 72)
    lines.append(f"AI Graph Intelligence has identified and clustered this coordinated")
    lines.append(f"fraud operation through automated analysis of transaction metadata,")
    lines.append(f"call records, and account linkages.")
    lines.append("")
    lines.append(f"  Total Identified Entities:    {len(entities)}")
    lines.append(f"  Total Correlated Incidents:   {len(incidents)}")
    lines.append(f"  Total Network Links:          {len(edges)}")

    # Fund flow total
    total_amount = sum(e.amount or 0.0 for e in edges)
    if total_amount > 0:
        lines.append(f"  Total Traced Fund Flow:       ₹{total_amount:,.2f}")
    lines.append("")

    # ─── ENTITY REGISTRY ──────────────────────────────────────────
    lines.append("SECTION 2: ENTITY REGISTRY")
    lines.append("-" * 72)
    for ent in entities:
        lines.append(f"  [{ent.type.upper():15s}] {ent.value}")
        lines.append(f"    Risk Score:     {ent.risk_score:.1f}/100")
        lines.append(f"    Centrality:     {ent.centrality_score:.4f}")
        lines.append(f"    PageRank:       {ent.pagerank_score:.4f}")
        lines.append(f"    Jurisdiction:   {ent.jurisdiction or 'Unknown'}")
        lines.append(f"    First Seen:     {ent.first_seen.strftime('%Y-%m-%d %H:%M:%S') if ent.first_seen else 'N/A'}")
        lines.append("")

    # ─── TRANSACTION LINKAGES ─────────────────────────────────────
    lines.append("SECTION 3: TRANSACTION LINKAGES & NETWORK EDGES")
    lines.append("-" * 72)
    for edge in edges:
        source = db.query(Entity).filter(Entity.id == edge.source_entity_id).first()
        target = db.query(Entity).filter(Entity.id == edge.target_entity_id).first()
        if source and target:
            amount_str = f"₹{edge.amount:,.2f}" if edge.amount else "N/A"
            lines.append(f"  {source.value} --[{edge.relationship_type}]--> {target.value}")
            lines.append(f"    Amount: {amount_str}  |  Weight: {edge.weight}  |  Direction: {edge.direction or 'undirected'}")
            lines.append("")

    # ─── INCIDENT TIMELINE ────────────────────────────────────────
    lines.append("SECTION 4: INCIDENT TIMELINE")
    lines.append("-" * 72)
    sorted_incidents = sorted(incidents, key=lambda x: x.timestamp or datetime.min)
    for inc in sorted_incidents:
        ts = inc.timestamp.strftime("%Y-%m-%d %H:%M:%S") if inc.timestamp else "N/A"
        lines.append(f"  [{inc.id}] {ts} | {inc.type} | Status: {inc.status} | Confidence: {inc.confidence}")
        lines.append(f"    Location: {inc.district or 'Unknown'} ({inc.lat}, {inc.lng})")
        lines.append("")

    # ─── CHAIN OF CUSTODY ─────────────────────────────────────────
    lines.append("SECTION 5: CHAIN OF CUSTODY & INTEGRITY")
    lines.append("-" * 72)
    lines.append("This intelligence package was generated dynamically by Project Sentinel")
    lines.append("Graph AI Engine. The content below is cryptographically hashed to ensure")
    lines.append("tamper-proof integrity for court submission under the Indian Evidence Act")
    lines.append("(Section 65B) and Information Technology Act, 2000.")
    lines.append("")

    # Build the full content string
    dossier_content = "\n".join(lines)

    # ─── COMPUTE SHA-256 HASH ─────────────────────────────────────
    sha256_hash = hashlib.sha256(dossier_content.encode("utf-8")).hexdigest()

    # Append the hash to the document itself
    dossier_content += f"\nSHA-256 INTEGRITY HASH: {sha256_hash}\n"
    dossier_content += "=" * 72 + "\n"
    dossier_content += "END OF DOSSIER\n"
    dossier_content += "=" * 72 + "\n"

    # ─── STORE IN DATABASE ────────────────────────────────────────
    package = EvidencePackage(
        campaign_id=campaign_id,
        incident_ids_json=json.dumps([inc.id for inc in incidents]),
        generated_at=timestamp,
        sha256_hash=sha256_hash,
        dossier_content=dossier_content
    )
    db.add(package)
    db.commit()
    db.refresh(package)

    return {
        "package_id": package.id,
        "sha256": sha256_hash,
        "content": dossier_content,
        "generated_at": timestamp_str,
        "entity_count": len(entities),
        "incident_count": len(incidents),
        "edge_count": len(edges)
    }
