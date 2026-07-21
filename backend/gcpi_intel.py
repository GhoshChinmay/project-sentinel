"""
GCPI Intel Package Generator — Project Sentinel
=================================================
Generates SHA-256 hashed inter-district intelligence briefs for the
Geospatial Crime Pattern Intelligence command centre.

Mirrors the evidence_engine.py pattern (text + SHA-256 hash).
"""

import hashlib
import json
from datetime import datetime, timedelta
from collections import Counter
from sqlalchemy.orm import Session
from models import GeoEvent
from gcpi_engine import GCPIPipeline


def generate_intel_package(db: Session, district: str, days: int = 30) -> dict:
    """
    Generates a shareable inter-district intelligence brief for the given district.

    Returns: {
        "district", "sha256", "content", "generated_at",
        "event_count", "hotspot_count"
    }
    """
    timestamp = datetime.utcnow()
    timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

    # --- Fetch GeoEvents for this district ---
    cutoff = timestamp - timedelta(days=days)
    events = db.query(GeoEvent).filter(
        GeoEvent.district == district,
        GeoEvent.timestamp >= cutoff,
        GeoEvent.lat.isnot(None),
        GeoEvent.lng.isnot(None),
    ).all()

    if not events:
        return {"error": f"No geo-events found for district '{district}' in the last {days} days."}

    # --- Run GCPI pipeline on this district's data ---
    event_dicts = [
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

    pipeline = GCPIPipeline(resolution=8)
    result = pipeline.run_full_pipeline(event_dicts, days)

    # --- Aggregate stats ---
    type_counts = Counter(ev.event_type for ev in events)
    source_counts = Counter(ev.source_module for ev in events)
    avg_severity = sum(ev.severity or 0 for ev in events) / len(events)
    hotspot_count = len(result.get("hotspots", []))
    emerging_count = len(result.get("emerging_clusters", []))

    # --- Build the intelligence brief ---
    lines = []
    lines.append("=" * 72)
    lines.append("GOVERNMENT OF INDIA — MINISTRY OF HOME AFFAIRS (I4C)")
    lines.append("INTER-DISTRICT INTELLIGENCE SHARING BRIEF")
    lines.append("GEOSPATIAL CRIME PATTERN INTELLIGENCE (GCPI)")
    lines.append("=" * 72)
    lines.append(f"GENERATED:        {timestamp_str}")
    lines.append(f"DISTRICT:         {district}")
    lines.append(f"ANALYSIS WINDOW:  Past {days} days")
    lines.append(f"CLASSIFICATION:   RESTRICTED — LAW ENFORCEMENT ONLY")
    lines.append("-" * 72)
    lines.append("")

    # --- Section 1: Executive Summary ---
    lines.append("SECTION 1: EXECUTIVE SUMMARY")
    lines.append("-" * 72)
    lines.append(f"Total Geo-Events:          {len(events)}")
    lines.append(f"Hotspot Cells (Gi*):       {hotspot_count}")
    lines.append(f"Emerging Clusters:         {emerging_count}")
    lines.append(f"Average Severity:          {avg_severity:.2f} / 1.00")
    lines.append(f"Max DCRI:                  {result['stats'].get('max_dcri', 'N/A')}")
    lines.append(f"Average DCRI:              {result['stats'].get('avg_dcri', 'N/A')}")
    lines.append("")

    # --- Section 2: Event Type Breakdown ---
    lines.append("SECTION 2: EVENT TYPE BREAKDOWN")
    lines.append("-" * 72)
    for event_type, count in type_counts.most_common():
        pct = (count / len(events)) * 100
        lines.append(f"  {event_type:25s}  {count:4d} events  ({pct:.1f}%)")
    lines.append("")

    # --- Section 3: Source Module Breakdown ---
    lines.append("SECTION 3: DATA SOURCE BREAKDOWN")
    lines.append("-" * 72)
    for source, count in source_counts.most_common():
        lines.append(f"  {source:25s}  {count:4d} events")
    lines.append("")

    # --- Section 4: Hotspot Analysis ---
    lines.append("SECTION 4: HOTSPOT ANALYSIS (Getis-Ord Gi*)")
    lines.append("-" * 72)
    if result.get("hotspots"):
        for i, h in enumerate(result["hotspots"][:5]):
            lines.append(f"  Hotspot #{i+1}:")
            lines.append(f"    Cell:    {h.get('cell_id', 'N/A')}")
            lines.append(f"    DCRI:    {h.get('dcri', 0)}")
            lines.append(f"    Events:  {h.get('event_count', 0)}")
            lines.append(f"    Gi* Z:   {h.get('gi_z_score', 0)}")
            lines.append("")
    else:
        lines.append("  No statistically significant hotspots detected.")
        lines.append("")

    # --- Section 5: Patrol Recommendations ---
    lines.append("SECTION 5: PATROL DEPLOYMENT RECOMMENDATIONS")
    lines.append("-" * 72)
    if result.get("patrol_allocation"):
        for alloc in result["patrol_allocation"][:5]:
            lines.append(f"  Sector {alloc.get('district', alloc['cell_id'][:12])}:")
            lines.append(f"    Priority Score:     {alloc.get('priority_score', 0)}")
            lines.append(f"    Recommendation:     {alloc.get('recommendation', 'MONITOR')}")
            lines.append(f"    Recommended Units:  {alloc.get('recommended_units', 1)}")
            lines.append("")
    else:
        lines.append("  No deployments recommended at this time.")
        lines.append("")

    # --- Section 6: Emerging Cluster Alerts ---
    lines.append("SECTION 6: EMERGING CLUSTER ALERTS (Kulldorff Scan)")
    lines.append("-" * 72)
    if result.get("emerging_clusters"):
        for i, cl in enumerate(result["emerging_clusters"][:3]):
            lines.append(f"  Alert #{i+1}: Relative Risk {cl.get('relative_risk', 0)}x baseline")
            lines.append(f"    Observed: {cl.get('observed', 0)} vs Expected: {cl.get('expected', 0)}")
            lines.append(f"    Log-Likelihood Ratio: {cl.get('llr', 0)}")
            lines.append("")
    else:
        lines.append("  No emerging clusters detected.")
        lines.append("")

    # --- Chain of Custody ---
    lines.append("SECTION 7: CHAIN OF CUSTODY & INTEGRITY")
    lines.append("-" * 72)
    lines.append("This intelligence package was generated dynamically by Project Sentinel")
    lines.append("GCPI Engine. The content below is cryptographically hashed to ensure")
    lines.append("tamper-proof integrity for inter-district sharing under the")
    lines.append("Information Technology Act, 2000.")
    lines.append("")

    # Build the full content string
    content = "\n".join(lines)

    # Compute SHA-256 hash
    sha256_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    # Append hash to the document
    content += f"\nSHA-256 INTEGRITY HASH: {sha256_hash}\n"
    content += "=" * 72 + "\n"
    content += "END OF INTELLIGENCE BRIEF\n"
    content += "=" * 72 + "\n"

    return {
        "district": district,
        "sha256": sha256_hash,
        "content": content,
        "generated_at": timestamp_str,
        "event_count": len(events),
        "hotspot_count": hotspot_count,
        "emerging_count": emerging_count,
    }
