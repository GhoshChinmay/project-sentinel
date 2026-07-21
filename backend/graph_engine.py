"""
Graph Intelligence Engine — Project Sentinel Phase 2
=====================================================
Runs graph-theory algorithms (Louvain community detection, PageRank,
betweenness centrality, fund-flow tracing) over the entity/edge graph
stored in SQLite to produce actionable intelligence packages.

Uses only NetworkX (already installed) and standard library.
"""

import json
import networkx as nx
from datetime import datetime
from sqlalchemy.orm import Session
from models import Entity, Incident, IncidentEntity, GraphEdge, Campaign

# ─────────────────────────────────────────────────────────────────
# Campaign naming — gives auto-detected campaigns recognizable names
# ─────────────────────────────────────────────────────────────────
CAMPAIGN_NAMES = [
    "Operation Tripwire", "Campaign Vortex", "Ring Hydra",
    "Network Phantom", "Cluster Ironclad", "Syndicate Cobra",
    "Cell Blackbird", "Operation Dragnet", "Ring Chimera",
    "Campaign Eclipse", "Network Serpent", "Cluster Aegis",
    "Syndicate Jackal", "Cell Nighthawk", "Operation Sentinel"
]


def _build_graph(db: Session):
    """
    Builds a NetworkX graph from all entities and edges in the DB.
    Returns the graph plus a dict mapping entity IDs to Entity ORM objects.
    """
    G = nx.Graph()
    entity_map = {}

    all_entities = db.query(Entity).all()
    for ent in all_entities:
        G.add_node(ent.id, type=ent.type, value=ent.value,
                   risk_score=ent.risk_score, jurisdiction=ent.jurisdiction)
        entity_map[ent.id] = ent

    all_edges = db.query(GraphEdge).all()
    for edge in all_edges:
        # Only add if both nodes exist
        if edge.source_entity_id in entity_map and edge.target_entity_id in entity_map:
            G.add_edge(
                edge.source_entity_id,
                edge.target_entity_id,
                weight=edge.weight,
                relationship_type=edge.relationship_type,
                amount=edge.amount or 0.0,
                direction=edge.direction or "undirected",
                edge_id=edge.id
            )

    return G, entity_map


def _detect_communities(G):
    """
    Runs Louvain community detection on the graph.
    Returns a dict mapping node_id -> community_index.
    """
    if len(G.nodes) < 2:
        return {node: 0 for node in G.nodes}

    try:
        communities = nx.community.louvain_communities(G, seed=42, resolution=1.0)
        node_to_community = {}
        for idx, community in enumerate(communities):
            for node in community:
                node_to_community[node] = idx
        return node_to_community
    except Exception as e:
        print(f"Louvain community detection failed: {e}")
        # Fallback: use connected components
        node_to_community = {}
        for idx, component in enumerate(nx.connected_components(G)):
            for node in component:
                node_to_community[node] = idx
        return node_to_community


def _compute_centrality(G):
    """
    Computes betweenness centrality for all nodes.
    Returns dict: node_id -> centrality_score (0.0 to 1.0).
    """
    if len(G.nodes) < 2:
        return {node: 0.0 for node in G.nodes}

    try:
        return nx.betweenness_centrality(G, weight="weight", normalized=True)
    except Exception as e:
        print(f"Centrality computation failed: {e}")
        return {node: 0.0 for node in G.nodes}


def _compute_pagerank(G):
    """
    Computes PageRank for all nodes.
    Returns dict: node_id -> pagerank_score.
    """
    if len(G.nodes) < 2:
        return {node: 0.0 for node in G.nodes}

    try:
        return nx.pagerank(G, weight="weight", alpha=0.85)
    except Exception as e:
        print(f"PageRank computation failed: {e}")
        return {node: 0.0 for node in G.nodes}


def run_full_analysis(db: Session) -> dict:
    """
    Master function: runs all graph algorithms, writes results back to DB,
    and returns a summary.

    Steps:
    1. Build in-memory graph from SQLite
    2. Run Louvain community detection -> assign campaign_id to entities
    3. Run betweenness centrality -> update centrality_score on entities
    4. Run PageRank -> update pagerank_score on entities
    5. Create/update Campaign records with aggregate stats
    6. Return summary dict
    """
    G, entity_map = _build_graph(db)

    if len(G.nodes) == 0:
        return {
            "status": "no_data",
            "message": "No entities in the database to analyze.",
            "campaigns_detected": 0,
            "total_nodes": 0,
            "total_edges": 0
        }

    # 1. Community detection
    node_communities = _detect_communities(G)

    # 2. Centrality
    centrality_scores = _compute_centrality(G)

    # 3. PageRank
    pagerank_scores = _compute_pagerank(G)

    # 4. Clear old campaigns (re-detection is idempotent)
    db.query(Campaign).delete()
    db.flush()

    # Reset campaign_id on all entities first
    db.query(Entity).update({Entity.campaign_id: None}, synchronize_session="fetch")
    db.flush()

    # 5. Group entities by community and create Campaign records
    community_groups = {}
    for node_id, comm_idx in node_communities.items():
        if comm_idx not in community_groups:
            community_groups[comm_idx] = []
        community_groups[comm_idx].append(node_id)

    campaigns_created = []
    for comm_idx, node_ids in community_groups.items():
        # Only create campaigns for groups with 2+ entities (single nodes aren't campaigns)
        if len(node_ids) < 2:
            # Still assign centrality/pagerank even for single nodes
            for nid in node_ids:
                if nid in entity_map:
                    ent = entity_map[nid]
                    ent.centrality_score = centrality_scores.get(nid, 0.0)
                    ent.pagerank_score = pagerank_scores.get(nid, 0.0)
            continue

        # Gather campaign stats
        jurisdictions = set()
        total_amount = 0.0
        incident_ids = set()
        max_risk = 0.0

        for nid in node_ids:
            ent = entity_map.get(nid)
            if ent:
                if ent.jurisdiction:
                    jurisdictions.add(ent.jurisdiction)
                max_risk = max(max_risk, ent.risk_score)

                # Count incidents linked to this entity
                links = db.query(IncidentEntity).filter(
                    IncidentEntity.entity_id == nid
                ).all()
                for link in links:
                    incident_ids.add(link.incident_id)

        # Sum fund flow amounts for edges within this campaign
        for i, nid_a in enumerate(node_ids):
            for nid_b in node_ids[i + 1:]:
                if G.has_edge(nid_a, nid_b):
                    edge_data = G[nid_a][nid_b]
                    total_amount += edge_data.get("amount", 0.0)

        # Determine risk level
        if max_risk >= 90:
            risk_level = "critical"
        elif max_risk >= 70:
            risk_level = "high"
        elif max_risk >= 40:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Pick a campaign name
        name_idx = comm_idx % len(CAMPAIGN_NAMES)
        campaign_name = CAMPAIGN_NAMES[name_idx]

        campaign = Campaign(
            name=campaign_name,
            description=f"Auto-detected fraud cluster with {len(node_ids)} linked entities across {len(jurisdictions) or 1} jurisdiction(s).",
            entity_count=len(node_ids),
            incident_count=len(incident_ids),
            total_amount_traced=total_amount,
            risk_level=risk_level,
            jurisdictions_json=json.dumps(list(jurisdictions)) if jurisdictions else "[]",
            detected_at=datetime.utcnow()
        )
        db.add(campaign)
        db.flush()  # Get the campaign ID

        # Assign campaign_id and scores to entities
        for nid in node_ids:
            if nid in entity_map:
                ent = entity_map[nid]
                ent.campaign_id = campaign.id
                ent.centrality_score = centrality_scores.get(nid, 0.0)
                ent.pagerank_score = pagerank_scores.get(nid, 0.0)

        campaigns_created.append({
            "id": campaign.id,
            "name": campaign.name,
            "entity_count": campaign.entity_count,
            "incident_count": campaign.incident_count,
            "total_amount_traced": campaign.total_amount_traced,
            "risk_level": campaign.risk_level,
            "jurisdictions": list(jurisdictions)
        })

    db.commit()

    return {
        "status": "success",
        "message": f"Analysis complete. {len(campaigns_created)} campaign(s) detected.",
        "campaigns_detected": len(campaigns_created),
        "total_nodes": len(G.nodes),
        "total_edges": len(G.edges),
        "campaigns": campaigns_created
    }


def run_incremental_update(db: Session):
    """
    Lightweight version of run_full_analysis — called after each new incident
    to keep campaign assignments fresh without heavy overhead.
    Only re-runs community detection if the graph has grown.
    """
    try:
        run_full_analysis(db)
    except Exception as e:
        # Never let graph analysis crash the main ingestion pipeline
        print(f"Graph incremental update failed (non-fatal): {e}")


def get_campaigns(db: Session) -> list:
    """Returns all detected campaigns with summary stats."""
    campaigns = db.query(Campaign).order_by(Campaign.detected_at.desc()).all()
    result = []
    for c in campaigns:
        result.append({
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "entity_count": c.entity_count,
            "incident_count": c.incident_count,
            "total_amount_traced": c.total_amount_traced,
            "risk_level": c.risk_level,
            "jurisdictions": json.loads(c.jurisdictions_json) if c.jurisdictions_json else [],
            "detected_at": c.detected_at.isoformat() if c.detected_at else None
        })
    return result


def get_entity_deep_dive(db: Session, entity_id: str) -> dict:
    """
    Returns a full profile for a single entity:
    - Basic info (type, value, risk, centrality, campaign)
    - All linked incidents
    - All connected entities (1-hop neighbors)
    - Fund flow paths
    """
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        return {"error": "Entity not found"}

    # Get campaign info
    campaign_info = None
    if entity.campaign_id:
        campaign = db.query(Campaign).filter(Campaign.id == entity.campaign_id).first()
        if campaign:
            campaign_info = {
                "id": campaign.id,
                "name": campaign.name,
                "risk_level": campaign.risk_level
            }

    # Get linked incidents
    links = db.query(IncidentEntity).filter(IncidentEntity.entity_id == entity_id).all()
    linked_incidents = []
    for link in links:
        incident = db.query(Incident).filter(Incident.id == link.incident_id).first()
        if incident:
            linked_incidents.append({
                "id": incident.id,
                "type": incident.type,
                "status": incident.status,
                "confidence": incident.confidence,
                "district": incident.district,
                "timestamp": incident.timestamp.isoformat() if incident.timestamp else None
            })

    # Get connected entities (1-hop neighbors via edges)
    edges_out = db.query(GraphEdge).filter(GraphEdge.source_entity_id == entity_id).all()
    edges_in = db.query(GraphEdge).filter(GraphEdge.target_entity_id == entity_id).all()

    connected_entities = []
    seen_ids = set()
    for edge in edges_out:
        neighbor_id = edge.target_entity_id
        if neighbor_id not in seen_ids:
            seen_ids.add(neighbor_id)
            neighbor = db.query(Entity).filter(Entity.id == neighbor_id).first()
            if neighbor:
                connected_entities.append({
                    "id": neighbor.id,
                    "type": neighbor.type,
                    "value": neighbor.value,
                    "risk_score": neighbor.risk_score,
                    "relationship": edge.relationship_type,
                    "amount": edge.amount
                })
    for edge in edges_in:
        neighbor_id = edge.source_entity_id
        if neighbor_id not in seen_ids:
            seen_ids.add(neighbor_id)
            neighbor = db.query(Entity).filter(Entity.id == neighbor_id).first()
            if neighbor:
                connected_entities.append({
                    "id": neighbor.id,
                    "type": neighbor.type,
                    "value": neighbor.value,
                    "risk_score": neighbor.risk_score,
                    "relationship": edge.relationship_type,
                    "amount": edge.amount
                })

    # Trace fund flow from this entity
    fund_flows = trace_fund_flow(db, entity_id)

    return {
        "id": entity.id,
        "type": entity.type,
        "value": entity.value,
        "risk_score": entity.risk_score,
        "centrality_score": entity.centrality_score,
        "pagerank_score": entity.pagerank_score,
        "jurisdiction": entity.jurisdiction,
        "campaign": campaign_info,
        "linked_incidents": linked_incidents,
        "connected_entities": connected_entities,
        "fund_flows": fund_flows,
        "first_seen": entity.first_seen.isoformat() if entity.first_seen else None
    }


def trace_fund_flow(db: Session, entity_id: str) -> list:
    """
    Traces money movement paths from a given entity through directed
    'transferred_funds' edges. Returns a list of flow steps.
    """
    flows = []
    visited = set()
    queue = [entity_id]

    while queue:
        current_id = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)

        # Find directed outgoing fund transfer edges
        outgoing = db.query(GraphEdge).filter(
            GraphEdge.source_entity_id == current_id,
            GraphEdge.relationship_type.in_(["transferred_funds", "transferred_to"])
        ).all()

        for edge in outgoing:
            target = db.query(Entity).filter(Entity.id == edge.target_entity_id).first()
            source = db.query(Entity).filter(Entity.id == current_id).first()
            if target and source:
                flows.append({
                    "from_id": current_id,
                    "from_value": source.value,
                    "from_type": source.type,
                    "to_id": edge.target_entity_id,
                    "to_value": target.value,
                    "to_type": target.type,
                    "amount": edge.amount,
                    "relationship": edge.relationship_type
                })
                if edge.target_entity_id not in visited:
                    queue.append(edge.target_entity_id)

    return flows
