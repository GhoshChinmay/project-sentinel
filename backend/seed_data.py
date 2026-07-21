import random
import json
import math
from datetime import datetime, timedelta
from database import engine, SessionLocal, Base
from models import Entity, Incident, IncidentEntity, GraphEdge, GeoEvent

# Create all tables (Campaign, Entity, Incident, GraphEdge, EvidencePackage, GeoEvent)
Base.metadata.create_all(bind=engine)

# Try to import h3 for cell computation; fall back to gcpi_engine's indexer
try:
    import h3
    def compute_h3(lat, lng):
        return h3.latlng_to_cell(lat, lng, 8)
except ImportError:
    from gcpi_engine import H3Indexer
    _indexer = H3Indexer(8)
    def compute_h3(lat, lng):
        return _indexer.latlng_to_cell(lat, lng)


def seed_database():
    db = SessionLocal()

    # Check if we already have data
    if db.query(Incident).first():
        print("Database already seeded. Skipping.")
        db.close()
        return

    print("Seeding synthetic data for Project Sentinel...")

    # ═══════════════════════════════════════════════════════════════
    # 1. Create Core Entities — 3 distinct fraud campaigns
    # ═══════════════════════════════════════════════════════════════

    # --- CAMPAIGN A: Digital Arrest Ring (Jamtara + Mewat based) ---
    campaign_a_entities = [
        {"type": "phone", "value": "+919876500001", "score": 95.0, "jurisdiction": "Jamtara"},    # Mastermind
        {"type": "phone", "value": "+919876500002", "score": 88.0, "jurisdiction": "Mewat"},      # Accomplice
        {"type": "upi", "value": "scammer1@ybl", "score": 99.0, "jurisdiction": "Jamtara"},       # Drop account
        {"type": "upi", "value": "mule_acc99@sbi", "score": 90.0, "jurisdiction": "Jamtara"},     # Mule layer 1
        {"type": "bank_account", "value": "HDFC000123456", "score": 75.0, "jurisdiction": "Mewat"},# Exit account
    ]

    # --- CAMPAIGN B: UPI Fraud Syndicate (Mumbai + Bengaluru based) ---
    campaign_b_entities = [
        {"type": "phone", "value": "+919123400010", "score": 92.0, "jurisdiction": "Mumbai Metro"},  # Recruiter
        {"type": "phone", "value": "+919123400011", "score": 85.0, "jurisdiction": "Mumbai Metro"},  # Caller 1
        {"type": "phone", "value": "+919123400012", "score": 78.0, "jurisdiction": "Bengaluru"},     # Caller 2
        {"type": "upi", "value": "quickpay.fraud@paytm", "score": 96.0, "jurisdiction": "Mumbai Metro"},  # Primary drop
        {"type": "upi", "value": "layering.mule2@ybl", "score": 88.0, "jurisdiction": "Bengaluru"},       # Mule layer
        {"type": "bank_account", "value": "ICIC000789012", "score": 82.0, "jurisdiction": "Bengaluru"},    # Layered exit
    ]

    # --- CAMPAIGN C: Customs Scam Cell (Delhi NCR based) ---
    campaign_c_entities = [
        {"type": "phone", "value": "+919555000020", "score": 97.0, "jurisdiction": "Delhi NCR"},    # Impersonator
        {"type": "phone", "value": "+919555000021", "score": 80.0, "jurisdiction": "Delhi NCR"},    # Runner
        {"type": "upi", "value": "customsfee@icici", "score": 94.0, "jurisdiction": "Delhi NCR"},   # Payment drop
        {"type": "bank_account", "value": "SBI0000345678", "score": 91.0, "jurisdiction": "Delhi NCR"},  # Collection
    ]

    all_campaign_entities = [
        ("A", campaign_a_entities),
        ("B", campaign_b_entities),
        ("C", campaign_c_entities)
    ]

    entity_objs = {}
    campaign_entity_ids = {"A": [], "B": [], "C": []}

    for campaign_label, entities_data in all_campaign_entities:
        for e in entities_data:
            entity = Entity(
                type=e["type"], value=e["value"],
                risk_score=e["score"], jurisdiction=e.get("jurisdiction")
            )
            db.add(entity)
            db.commit()
            db.refresh(entity)
            entity_objs[e["value"]] = entity
            campaign_entity_ids[campaign_label].append(entity)

    # ═══════════════════════════════════════════════════════════════
    # 2. Locations (For Geospatial Map)
    # ═══════════════════════════════════════════════════════════════
    locations = [
        {"district": "Jamtara", "lat": 23.9632, "lng": 86.8023},
        {"district": "Mewat", "lat": 28.0202, "lng": 77.0004},
        {"district": "Mumbai Metro", "lat": 19.0760, "lng": 72.8777},
        {"district": "Delhi NCR", "lat": 28.7041, "lng": 77.1025},
        {"district": "Bengaluru", "lat": 12.9716, "lng": 77.5946}
    ]

    # ═══════════════════════════════════════════════════════════════
    # 3. Create Historical Incidents & Link Entities
    # ═══════════════════════════════════════════════════════════════
    for i in range(1, 41):
        loc = random.choice(locations)
        time_offset = timedelta(days=random.randint(0, 7), hours=random.randint(0, 23))

        status = "critical" if random.random() > 0.3 else "warning"
        inc_type = random.choice(["scam_call", "citizen_report"])

        inc = Incident(
            id=f"INC-{1000+i}",
            type=inc_type,
            status=status,
            confidence=f"{random.randint(85, 99)}%",
            raw_payload_json='{"details": "Synthetic historical data"}',
            lat=loc["lat"] + random.uniform(-0.05, 0.05),
            lng=loc["lng"] + random.uniform(-0.05, 0.05),
            district=loc["district"],
            timestamp=datetime.utcnow() - time_offset
        )
        db.add(inc)

        # Link 1-2 random entities from ONE campaign to this incident
        # This ensures entities cluster properly within their campaign
        campaign_label = random.choice(["A", "B", "C"])
        available_entities = campaign_entity_ids[campaign_label]
        num_to_link = min(random.randint(1, 2), len(available_entities))
        linked_entities = random.sample(available_entities, num_to_link)
        for ent in linked_entities:
            link = IncidentEntity(incident_id=inc.id, entity_id=ent.id, role="suspect")
            db.add(link)

    # ═══════════════════════════════════════════════════════════════
    # 4. Create Graph Edges — Rich Relationships with Fund Flows
    # ═══════════════════════════════════════════════════════════════

    # --- Campaign A: Digital Arrest Ring edges ---
    edges_a = [
        # Mastermind owns the drop UPI
        ("+919876500001", "scammer1@ybl", "owns_account", 1.0, None, "directed"),
        # Mastermind calls accomplice
        ("+919876500001", "+919876500002", "shared_session", 1.5, None, "undirected"),
        # Money flows: drop → mule → exit
        ("scammer1@ybl", "mule_acc99@sbi", "transferred_funds", 1.0, 245000.0, "directed"),
        ("mule_acc99@sbi", "HDFC000123456", "transferred_funds", 1.0, 230000.0, "directed"),
        # Accomplice linked to exit account
        ("+919876500002", "HDFC000123456", "owns_account", 1.0, None, "directed"),
    ]

    # --- Campaign B: UPI Fraud Syndicate edges ---
    edges_b = [
        # Recruiter coordinates callers
        ("+919123400010", "+919123400011", "shared_device", 2.0, None, "undirected"),
        ("+919123400010", "+919123400012", "shared_sim", 1.0, None, "undirected"),
        # Callers point victims to primary drop
        ("+919123400011", "quickpay.fraud@paytm", "owns_account", 1.0, None, "directed"),
        # Fund flow: primary drop → mule → exit
        ("quickpay.fraud@paytm", "layering.mule2@ybl", "transferred_funds", 1.0, 180000.0, "directed"),
        ("layering.mule2@ybl", "ICIC000789012", "transferred_funds", 1.0, 165000.0, "directed"),
        # Cross-link: caller 2 also uses mule
        ("+919123400012", "layering.mule2@ybl", "owns_account", 1.0, None, "directed"),
    ]

    # --- Campaign C: Customs Scam Cell edges ---
    edges_c = [
        # Impersonator coordinates runner
        ("+919555000020", "+919555000021", "shared_session", 1.5, None, "undirected"),
        # Impersonator directs payments to drop
        ("+919555000020", "customsfee@icici", "owns_account", 1.0, None, "directed"),
        # Fund flow: drop → collection
        ("customsfee@icici", "SBI0000345678", "transferred_funds", 1.0, 520000.0, "directed"),
        # Runner also linked to collection account
        ("+919555000021", "SBI0000345678", "owns_account", 1.0, None, "directed"),
    ]

    all_edges = edges_a + edges_b + edges_c
    for source_val, target_val, rel_type, weight, amount, direction in all_edges:
        source_entity = entity_objs[source_val]
        target_entity = entity_objs[target_val]
        edge = GraphEdge(
            source_entity_id=source_entity.id,
            target_entity_id=target_entity.id,
            relationship_type=rel_type,
            weight=weight,
            amount=amount,
            direction=direction
        )
        db.add(edge)

    db.commit()
    print("✅ Seed complete! 40 historical incidents, 15 entities across 3 campaigns, and rich fund-flow edges created.")

    # ═══════════════════════════════════════════════════════════════
    # 5. Run graph analysis so Campaign/centrality data is populated
    #    for the Graph Intelligence tab out of the box (best-effort).
    # ═══════════════════════════════════════════════════════════════
    try:
        from graph_engine import run_full_analysis
        run_full_analysis(db)
        print("✅ Graph analysis complete — campaigns, centrality & PageRank populated.")
    except Exception as e:
        print(f"⚠️  Graph analysis skipped (run POST /api/graph/analyze later): {e}")

    db.close()


# ============================================================================
# GCPI GEO EVENTS SEEDER
# ============================================================================

# Expanded city list: 15 Indian cities with realistic scam profiles
CITIES = [
    # Scam hubs (high mule_node, high complaint density)
    {"district": "Jamtara", "lat": 23.9632, "lng": 86.8023,
     "weights": {"complaint": 0.25, "scam_call_alert": 0.30, "mule_node": 0.35, "seizure": 0.10}},
    {"district": "Mewat", "lat": 28.0202, "lng": 77.0004,
     "weights": {"complaint": 0.20, "scam_call_alert": 0.35, "mule_node": 0.30, "seizure": 0.15}},

    # Tier-1 metros (high complaint volume, moderate mule nodes)
    {"district": "Mumbai Metro", "lat": 19.0760, "lng": 72.8777,
     "weights": {"complaint": 0.45, "scam_call_alert": 0.25, "mule_node": 0.15, "seizure": 0.15}},
    {"district": "Delhi NCR", "lat": 28.7041, "lng": 77.1025,
     "weights": {"complaint": 0.40, "scam_call_alert": 0.25, "mule_node": 0.15, "seizure": 0.20}},
    {"district": "Bengaluru", "lat": 12.9716, "lng": 77.5946,
     "weights": {"complaint": 0.45, "scam_call_alert": 0.20, "mule_node": 0.15, "seizure": 0.20}},
    {"district": "Hyderabad", "lat": 17.3850, "lng": 78.4867,
     "weights": {"complaint": 0.40, "scam_call_alert": 0.25, "mule_node": 0.15, "seizure": 0.20}},
    {"district": "Chennai", "lat": 13.0827, "lng": 80.2707,
     "weights": {"complaint": 0.40, "scam_call_alert": 0.25, "mule_node": 0.15, "seizure": 0.20}},
    {"district": "Kolkata", "lat": 22.5726, "lng": 88.3639,
     "weights": {"complaint": 0.35, "scam_call_alert": 0.30, "mule_node": 0.20, "seizure": 0.15}},

    # Tier-2 cities
    {"district": "Pune", "lat": 18.5204, "lng": 73.8567,
     "weights": {"complaint": 0.40, "scam_call_alert": 0.25, "mule_node": 0.15, "seizure": 0.20}},
    {"district": "Ahmedabad", "lat": 23.0225, "lng": 72.5714,
     "weights": {"complaint": 0.35, "scam_call_alert": 0.25, "mule_node": 0.20, "seizure": 0.20}},
    {"district": "Lucknow", "lat": 26.8467, "lng": 80.9462,
     "weights": {"complaint": 0.40, "scam_call_alert": 0.25, "mule_node": 0.15, "seizure": 0.20}},
    {"district": "Jaipur", "lat": 26.9124, "lng": 75.7873,
     "weights": {"complaint": 0.35, "scam_call_alert": 0.25, "mule_node": 0.20, "seizure": 0.20}},
    {"district": "Chandigarh", "lat": 30.7333, "lng": 76.7794,
     "weights": {"complaint": 0.40, "scam_call_alert": 0.25, "mule_node": 0.15, "seizure": 0.20}},
    {"district": "Kochi", "lat": 9.9312, "lng": 76.2673,
     "weights": {"complaint": 0.35, "scam_call_alert": 0.25, "mule_node": 0.15, "seizure": 0.25}},
    {"district": "Indore", "lat": 22.7196, "lng": 75.8577,
     "weights": {"complaint": 0.35, "scam_call_alert": 0.25, "mule_node": 0.20, "seizure": 0.20}},
]

SOURCE_MODULES = {
    "complaint": ["ncrp", "cctns", "field_app"],
    "seizure": ["ficn_seizure", "cctns"],
    "scam_call_alert": ["telecom_alert", "ncrp"],
    "mule_node": ["fraud_graph", "cctns"],
}

GEO_CONFIDENCE_LEVELS = ["exact", "tower", "address"]


def seed_geo_events():
    """
    Seeds 200+ realistic GeoEvent records across 15 Indian cities.
    Distribution:
    - Scam hubs (Jamtara, Mewat): ~30 events each with high mule_node density
    - Tier-1 metros: ~20 events each with high complaint volume
    - Tier-2 cities: ~10 events each with balanced distribution
    Temporal: 30-day spread with salary-day spikes (1st, 15th) and weekend dips
    """
    db = SessionLocal()

    # Check if we already have geo events
    if db.query(GeoEvent).first():
        print("GeoEvents already seeded. Skipping.")
        db.close()
        return

    print("Seeding GCPI GeoEvent data across 15 Indian cities...")

    now = datetime.utcnow()
    events_created = 0

    # Per-city event counts: scam hubs get more events
    city_event_counts = {}
    for city in CITIES:
        d = city["district"]
        if d in ["Jamtara", "Mewat"]:
            city_event_counts[d] = random.randint(28, 35)
        elif d in ["Mumbai Metro", "Delhi NCR", "Bengaluru", "Hyderabad", "Chennai", "Kolkata"]:
            city_event_counts[d] = random.randint(18, 24)
        else:
            city_event_counts[d] = random.randint(8, 14)

    for city in CITIES:
        district = city["district"]
        base_lat = city["lat"]
        base_lng = city["lng"]
        weights = city["weights"]
        n_events = city_event_counts[district]

        event_types_list = list(weights.keys())
        event_weights = [weights[t] for t in event_types_list]

        for i in range(n_events):
            # Pick event type based on city-specific distribution
            event_type = random.choices(event_types_list, weights=event_weights, k=1)[0]

            # Scatter coordinates around the city centre (0.15° ≈ 17km radius)
            scatter = 0.15
            lat = base_lat + random.uniform(-scatter, scatter)
            lng = base_lng + random.uniform(-scatter, scatter)

            # Create slight clustering within city (some events near each other)
            if random.random() < 0.3 and i > 0:
                # Cluster near a previous event
                lat = base_lat + random.uniform(-0.03, 0.03)
                lng = base_lng + random.uniform(-0.03, 0.03)

            # Temporal distribution (30 days back)
            day_offset = random.randint(0, 29)
            hour = random.randint(0, 23)

            # Salary-day spikes: 2x events on 1st and 15th
            current_day = (now - timedelta(days=day_offset)).day
            if current_day in [1, 2, 15, 16]:
                # Extra events on salary days — add a duplicate later
                pass

            # Weekend dip: fewer events on weekends
            weekday = (now - timedelta(days=day_offset)).weekday()
            if weekday >= 5 and random.random() < 0.4:
                continue  # Skip some weekend events

            ts = now - timedelta(days=day_offset, hours=hour, minutes=random.randint(0, 59))

            # Severity based on event type
            severity_map = {
                "complaint": random.uniform(0.3, 0.8),
                "seizure": random.uniform(0.6, 1.0),
                "scam_call_alert": random.uniform(0.5, 0.9),
                "mule_node": random.uniform(0.7, 1.0),
            }
            severity = severity_map.get(event_type, 0.5)

            # Source module
            source = random.choice(SOURCE_MODULES.get(event_type, ["ncrp"]))

            # Geo confidence
            geo_conf = random.choices(
                GEO_CONFIDENCE_LEVELS,
                weights=[0.5, 0.3, 0.2],
                k=1
            )[0]

            # Compute H3 cell
            h3_cell = compute_h3(lat, lng)

            # Entity refs (random FIR/case IDs)
            entity_refs = []
            if event_type == "complaint":
                entity_refs = [f"FIR-{district[:3].upper()}-{random.randint(1000, 9999)}"]
            elif event_type == "mule_node":
                entity_refs = [f"ENT-{random.randint(10000, 99999)}"]
            elif event_type == "seizure":
                entity_refs = [f"FICN-{random.randint(100, 999)}"]

            geo_event = GeoEvent(
                source_module=source,
                event_type=event_type,
                lat=round(lat, 6),
                lng=round(lng, 6),
                h3_cell=h3_cell,
                geo_confidence=geo_conf,
                timestamp=ts,
                severity=round(severity, 2),
                entity_refs_json=json.dumps(entity_refs),
                district=district,
            )
            db.add(geo_event)
            events_created += 1

        # Add extra salary-day burst events for metros
        if district in ["Mumbai Metro", "Delhi NCR", "Bengaluru", "Hyderabad"]:
            for _ in range(random.randint(3, 6)):
                event_type = random.choices(event_types_list, weights=event_weights, k=1)[0]
                lat = base_lat + random.uniform(-0.1, 0.1)
                lng = base_lng + random.uniform(-0.1, 0.1)
                # Pick a salary day
                salary_day_offset = random.choice([d for d in range(30) if (now - timedelta(days=d)).day in [1, 2, 15, 16]])
                ts = now - timedelta(days=salary_day_offset, hours=random.randint(9, 18))

                h3_cell = compute_h3(lat, lng)
                severity = random.uniform(0.5, 0.9)
                source = random.choice(SOURCE_MODULES.get(event_type, ["ncrp"]))

                geo_event = GeoEvent(
                    source_module=source,
                    event_type=event_type,
                    lat=round(lat, 6),
                    lng=round(lng, 6),
                    h3_cell=h3_cell,
                    geo_confidence="exact",
                    timestamp=ts,
                    severity=round(severity, 2),
                    entity_refs_json="[]",
                    district=district,
                )
                db.add(geo_event)
                events_created += 1

    db.commit()
    db.close()
    print(f"GCPI Seed complete! {events_created} GeoEvent records created across {len(CITIES)} cities.")


if __name__ == "__main__":
    seed_database()
    seed_geo_events()
