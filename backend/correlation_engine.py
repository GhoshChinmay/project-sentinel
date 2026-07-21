import networkx as nx
from datetime import datetime
from sqlalchemy.orm import Session
from models import Entity, Incident, IncidentEntity, GraphEdge

# Lazy import to avoid circular dependency
def _get_graph_engine():
    try:
        import graph_engine
        return graph_engine
    except ImportError:
        return None

def correlate_and_cluster(db: Session, incident_id: str, extracted_entities: dict, incident_district: str = None):
    """
    Saves extracted entities, builds/updates their relationship edges, and runs
    BOTH graph-intelligence layers over SQLite in a single pass:

      • Fraud-Graph (Fork A): jurisdiction tagging, lead-time intelligence and an
        incremental campaign/centrality refresh via graph_engine.
      • Filter-then-Verify GNN (Fork B): degree-centrality, Sybil-ring detection
        and mule-network distance ('arXiv:2605.17201').

    Returns a superset dict so every caller keeps its expected keys:
        {has_prior_clusters, lead_time_minutes,
         structural_threat, degree_centrality, mule_network_distance}
    """
    # 1. Flatten all raw entities extracted from the NLP engine
    items_to_process = []
    for val in extracted_entities.get("phone_numbers", []):
        items_to_process.append(("phone", val))
    for val in extracted_entities.get("upi_ids", []):
        items_to_process.append(("upi", val))
    for val in extracted_entities.get("bank_accounts", []):
        items_to_process.append(("bank_account", val))
    for val in extracted_entities.get("institutions", []):
        items_to_process.append(("institution", val))
    for val in extracted_entities.get("person_names", []):
        items_to_process.append(("person", val))

    db_entities = []

    # 2. Match or Insert unique entities into the DB
    for ent_type, val in items_to_process:
        # Check if already exists in DB
        entity = db.query(Entity).filter(Entity.value == val).first()
        if not entity:
            entity = Entity(
                type=ent_type, value=val, risk_score=85.0,
                jurisdiction=incident_district  # Tag jurisdiction from incident location
            )
            db.add(entity)
            db.commit()
            db.refresh(entity)
        else:
            # Update jurisdiction if entity didn't have one
            if not entity.jurisdiction and incident_district:
                entity.jurisdiction = incident_district
                db.commit()
        db_entities.append(entity)

        # Link this entity to our new Incident if not already linked
        link = db.query(IncidentEntity).filter(
            IncidentEntity.incident_id == incident_id,
            IncidentEntity.entity_id == entity.id
        ).first()
        if not link:
            link = IncidentEntity(incident_id=incident_id, entity_id=entity.id, role="suspect")
            db.add(link)
            db.commit()

    # 3. Create bidirectional edges between all co-occurring entities in this incident
    for i in range(len(db_entities)):
        for j in range(i + 1, len(db_entities)):
            ent_a, ent_b = db_entities[i], db_entities[j]
            # Ensure order to prevent duplicates (A -> B is same as B -> A in undirected representation)
            source_id, target_id = sorted([ent_a.id, ent_b.id])

            edge = db.query(GraphEdge).filter(
                GraphEdge.source_entity_id == source_id,
                GraphEdge.target_entity_id == target_id
            ).first()

            if not edge:
                edge = GraphEdge(
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    relationship_type="shared_session",
                    weight=1.0
                )
                db.add(edge)
                db.commit()
            else:
                # Strengthen weight if observed multiple times
                edge.weight += 0.5
                db.commit()

    # 4. Graph analytics — computed once over a single in-memory graph
    lead_time_info = {"has_prior_clusters": False, "lead_time_minutes": 0}
    gnn_metrics = {
        "structural_threat": "Low",
        "degree_centrality": 0,
        "mule_network_distance": "Safe"
    }

    if len(db_entities) > 0:
        # Build an in-memory graph from our SQLite edges (shared by both layers)
        G = nx.Graph()
        all_edges = db.query(GraphEdge).all()
        for edge in all_edges:
            G.add_edge(edge.source_entity_id, edge.target_entity_id, weight=edge.weight)

        # ─── Fork A: Lead-time intelligence over the connected component ───
        connected_entities = set()
        for ent in db_entities:
            if ent.id in G:
                connected_entities.update(nx.node_connected_component(G, ent.id))

        if len(connected_entities) > 0:
            # Look up all historical critical incidents linked to these connected nodes
            prior_incidents = db.query(Incident).join(IncidentEntity).filter(
                IncidentEntity.entity_id.in_(list(connected_entities)),
                Incident.status == "critical",
                Incident.id != incident_id
            ).order_by(Incident.timestamp.asc()).all()

            if len(prior_incidents) > 0:
                first_flag_time = prior_incidents[0].timestamp
                current_time = datetime.utcnow()
                delta = current_time - first_flag_time

                lead_time_info["has_prior_clusters"] = True
                lead_time_info["lead_time_minutes"] = max(1, int(delta.total_seconds() / 60))

        # ─── Fork B: Filter-then-Verify GNN structural metrics ───
        max_centrality = 0
        is_connected_to_mule = False
        for ent in db_entities:
            if ent.id in G:
                # SOTA METRIC 1: Degree Centrality (Is this node a central hub for multiple scams?)
                centrality = G.degree(ent.id)
                if centrality > max_centrality:
                    max_centrality = centrality

                # SOTA METRIC 2: Sybil Network Detection (Connected components)
                connected_nodes = nx.node_connected_component(G, ent.id)
                if len(connected_nodes) > 3:
                    is_connected_to_mule = True

        gnn_metrics["degree_centrality"] = max_centrality
        if max_centrality >= 3 or is_connected_to_mule:
            gnn_metrics["structural_threat"] = "CRITICAL (Sybil Ring Detected)"
            gnn_metrics["mule_network_distance"] = "Direct Link"
        elif max_centrality > 0:
            gnn_metrics["structural_threat"] = "Warning (1-Hop Match)"
            gnn_metrics["mule_network_distance"] = "1-Hop Away"

    # ─── Fork A: Trigger incremental graph analysis (keeps campaign + centrality
    # assignments fresh after every new incident). Wrapped so it never crashes
    # the main ingestion pipeline. ───
    if len(db_entities) > 0:
        ge = _get_graph_engine()
        if ge:
            try:
                ge.run_incremental_update(db)
            except Exception as e:
                print(f"⚠️  Incremental graph update skipped: {e}")

    # Merge both analytics layers into one response
    return {**lead_time_info, **gnn_metrics}
