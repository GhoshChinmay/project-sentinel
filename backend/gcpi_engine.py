"""
GCPI Engine — Geospatial Crime Pattern Intelligence
Core analytics engine for Project Sentinel Phase 1.

Provides:
- H3 hexagonal spatial indexing
- Getis-Ord Gi* hotspot statistics
- HDBSCAN density-adaptive clustering
- Kulldorff spatial scan statistics
- Digital Crime Risk Index (DCRI) fusion scoring
- Per-cell time-series forecasting (exponential smoothing)
- Patrol allocation ranking
"""

import math
import hashlib
import numpy as np
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import Optional

# --- H3 Indexer ---
# We try importing h3; if unavailable, fall back to a pure-Python hex approximation

try:
    import h3
    H3_AVAILABLE = True
except ImportError:
    H3_AVAILABLE = False

try:
    import hdbscan as hdbscan_lib
    HDBSCAN_AVAILABLE = True
except ImportError:
    HDBSCAN_AVAILABLE = False
    from sklearn.cluster import DBSCAN

from scipy import stats as scipy_stats
from scipy.spatial.distance import cdist


# ============================================================================
# H3 HEXAGONAL SPATIAL INDEXER
# ============================================================================

class H3Indexer:
    """Converts lat/lng to H3 cells. Falls back to geohash-style grid if h3 is missing."""

    def __init__(self, resolution: int = 8):
        self.resolution = resolution
        # H3 res 8 ≈ 0.74 km² hexagons

    def latlng_to_cell(self, lat: float, lng: float) -> str:
        if H3_AVAILABLE:
            return h3.latlng_to_cell(lat, lng, self.resolution)
        else:
            return self._fallback_cell(lat, lng)

    def cell_to_boundary(self, cell_id: str) -> list:
        """Returns list of [lat, lng] pairs defining the hex boundary."""
        if H3_AVAILABLE:
            boundary = h3.cell_to_boundary(cell_id)
            return [[lat, lng] for lat, lng in boundary]
        else:
            return self._fallback_boundary(cell_id)

    def cell_to_latlng(self, cell_id: str) -> tuple:
        """Returns (lat, lng) centre of the cell."""
        if H3_AVAILABLE:
            return h3.cell_to_latlng(cell_id)
        else:
            return self._fallback_center(cell_id)

    def k_ring(self, cell_id: str, k: int = 1) -> set:
        """Returns the set of cells within k hops of cell_id."""
        if H3_AVAILABLE:
            return h3.grid_disk(cell_id, k)
        else:
            return self._fallback_kring(cell_id, k)

    # --- Fallback pure-Python hex grid (deterministic geohash-style) ---
    def _fallback_cell(self, lat: float, lng: float) -> str:
        """Approximate hexagonal cell using a simple grid quantisation."""
        # Cell size scaling based on resolution
        cell_size = 1.0 / (2 ** (self.resolution - 4))  # res 8 → 1/16 ≈ 0.0625 degrees ≈ 7 km
        row = int(math.floor(lat / cell_size))
        col = int(math.floor(lng / cell_size))
        # Offset odd rows for hex effect
        if row % 2 != 0:
            col = int(math.floor((lng + cell_size / 2) / cell_size))
        return f"fallback_{self.resolution}_{row}_{col}"

    def _fallback_boundary(self, cell_id: str) -> list:
        parts = cell_id.split("_")
        res = int(parts[1])
        row = int(parts[2])
        col = int(parts[3])
        cell_size = 1.0 / (2 ** (res - 4))
        clat = row * cell_size + cell_size / 2
        clng = col * cell_size + cell_size / 2
        if row % 2 != 0:
            clng -= cell_size / 2
        # Hexagon vertices
        r = cell_size / 2
        return [
            [clat + r, clng],
            [clat + r / 2, clng + r * 0.866],
            [clat - r / 2, clng + r * 0.866],
            [clat - r, clng],
            [clat - r / 2, clng - r * 0.866],
            [clat + r / 2, clng - r * 0.866],
        ]

    def _fallback_center(self, cell_id: str) -> tuple:
        parts = cell_id.split("_")
        row = int(parts[2])
        col = int(parts[3])
        res = int(parts[1])
        cell_size = 1.0 / (2 ** (res - 4))
        clat = row * cell_size + cell_size / 2
        clng = col * cell_size + cell_size / 2
        if row % 2 != 0:
            clng -= cell_size / 2
        return (clat, clng)

    def _fallback_kring(self, cell_id: str, k: int) -> set:
        parts = cell_id.split("_")
        res = int(parts[1])
        row = int(parts[2])
        col = int(parts[3])
        ring = set()
        for dr in range(-k, k + 1):
            for dc in range(-k, k + 1):
                ring.add(f"fallback_{res}_{row + dr}_{col + dc}")
        return ring


# ============================================================================
# GETIS-ORD Gi* HOTSPOT STATISTICS
# ============================================================================

class GiStarCalculator:
    """
    Computes Getis-Ord Gi* z-scores per H3 cell against k-ring neighbours.
    High positive z → statistically significant hotspot.
    High negative z → cold spot.
    """

    def __init__(self, indexer: H3Indexer, k: int = 1):
        self.indexer = indexer
        self.k = k

    def compute(self, cell_counts: dict) -> dict:
        """
        cell_counts: {cell_id: event_count}
        Returns: {cell_id: {z_score, p_value, is_hot, is_cold}}
        """
        if not cell_counts:
            return {}

        all_cells = list(cell_counts.keys())
        values = np.array([cell_counts[c] for c in all_cells])
        n = len(values)
        if n < 3:
            return {c: {"z_score": 0, "p_value": 1.0, "is_hot": False, "is_cold": False} for c in all_cells}

        x_bar = values.mean()
        s = values.std()
        if s == 0:
            return {c: {"z_score": 0, "p_value": 1.0, "is_hot": False, "is_cold": False} for c in all_cells}

        results = {}
        for i, cell in enumerate(all_cells):
            neighbours = self.indexer.k_ring(cell, self.k)
            w_sum = 0.0
            w_count = 0
            for j, other in enumerate(all_cells):
                if other in neighbours:
                    w_sum += values[j]
                    w_count += 1

            if w_count == 0:
                results[cell] = {"z_score": 0, "p_value": 1.0, "is_hot": False, "is_cold": False}
                continue

            numerator = w_sum - x_bar * w_count
            denominator = s * math.sqrt((n * w_count - w_count ** 2) / (n - 1)) if n > 1 else 1.0
            z = numerator / denominator if denominator > 0 else 0.0
            p = 2 * (1 - scipy_stats.norm.cdf(abs(z)))

            results[cell] = {
                "z_score": float(round(z, 3)),
                "p_value": float(round(p, 4)),
                "is_hot": bool(z > 1.96),  # 95% confidence
                "is_cold": bool(z < -1.96),
            }

        return results


# ============================================================================
# HDBSCAN DENSITY-ADAPTIVE CLUSTERING
# ============================================================================

class HDBSCANClusterer:
    """Density-adaptive spatial clustering. Falls back to DBSCAN if hdbscan not installed."""

    def __init__(self, min_cluster_size: int = 3, min_samples: int = 2):
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples

    def cluster(self, coords: np.ndarray) -> np.ndarray:
        """
        coords: Nx2 array of [lat, lng]
        Returns: array of cluster labels (-1 = noise)
        """
        if len(coords) < self.min_cluster_size:
            return np.full(len(coords), -1)

        if HDBSCAN_AVAILABLE:
            clusterer = hdbscan_lib.HDBSCAN(
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
                metric='haversine',
                algorithm='best'
            )
            # HDBSCAN with haversine expects radians
            coords_rad = np.radians(coords)
            return clusterer.fit_predict(coords_rad)
        else:
            # Fallback to DBSCAN
            dbscan = DBSCAN(eps=0.05, min_samples=self.min_samples).fit(coords)
            return dbscan.labels_


# ============================================================================
# KULLDORFF SPATIAL SCAN STATISTIC
# ============================================================================

class KulldorffScanner:
    """
    Simplified Kulldorff spatial scan for emerging cluster detection.
    Scans circular windows of increasing radius around each cell,
    looking for regions where observed counts significantly exceed expected.
    """

    def __init__(self, indexer: H3Indexer, max_radius: int = 3, p_threshold: float = 0.05):
        self.indexer = indexer
        self.max_radius = max_radius
        self.p_threshold = p_threshold

    def scan(self, cell_counts: dict, cell_baselines: Optional[dict] = None) -> list:
        """
        cell_counts: {cell_id: current_count}
        cell_baselines: {cell_id: expected_count} (defaults to global mean)
        Returns: list of emerging cluster dicts sorted by log-likelihood ratio
        """
        if not cell_counts:
            return []

        all_cells = list(cell_counts.keys())
        total_c = sum(cell_counts.values())
        n = len(all_cells)

        if total_c == 0 or n < 2:
            return []

        global_rate = total_c / n
        if cell_baselines is None:
            cell_baselines = {c: global_rate for c in all_cells}

        clusters = []
        for cell in all_cells:
            for r in range(1, self.max_radius + 1):
                window = self.indexer.k_ring(cell, r)
                window_cells = [c for c in all_cells if c in window]

                observed = sum(cell_counts.get(c, 0) for c in window_cells)
                expected = sum(cell_baselines.get(c, global_rate) for c in window_cells)

                if expected <= 0 or observed <= expected:
                    continue

                # Log-likelihood ratio
                llr = observed * math.log(observed / expected) if observed > 0 else 0
                remainder_obs = total_c - observed
                remainder_exp = total_c - expected
                if remainder_exp > 0 and remainder_obs > 0:
                    llr += remainder_obs * math.log(remainder_obs / remainder_exp)

                if llr > 2.0:  # Significance threshold
                    center_latlng = self.indexer.cell_to_latlng(cell)
                    clusters.append({
                        "center_cell": cell,
                        "center_lat": float(round(center_latlng[0], 4)),
                        "center_lng": float(round(center_latlng[1], 4)),
                        "radius_k": int(r),
                        "observed": int(observed),
                        "expected": float(round(expected, 2)),
                        "llr": float(round(llr, 3)),
                        "relative_risk": float(round(observed / expected, 2)) if expected > 0 else 0.0,
                        "cells_in_window": int(len(window_cells)),
                    })

        # Deduplicate overlapping clusters — keep highest LLR
        clusters.sort(key=lambda x: x["llr"], reverse=True)
        used_cells = set()
        unique_clusters = []
        for cl in clusters:
            if cl["center_cell"] not in used_cells:
                unique_clusters.append(cl)
                window = self.indexer.k_ring(cl["center_cell"], cl["radius_k"])
                used_cells.update(window)

        return unique_clusters[:10]  # Top 10 emerging clusters


# ============================================================================
# DIGITAL CRIME RISK INDEX (DCRI)
# ============================================================================

class DCRICalculator:
    """
    Computes Digital Crime Risk Index per H3 cell as a weighted fusion of 4 signal types.
    DCRI = w1*complaint_density + w2*seizure_density + w3*scam_density + w4*mule_density + forecast_delta
    Normalised to 0–100 scale.
    """

    WEIGHTS = {
        "complaint": 0.30,
        "seizure": 0.25,
        "scam_call_alert": 0.25,
        "mule_node": 0.20,
    }

    def compute(self, cell_type_counts: dict, forecast_deltas: Optional[dict] = None) -> dict:
        """
        cell_type_counts: {cell_id: {event_type: count}}
        forecast_deltas: {cell_id: delta_value} (positive = increasing trend)
        Returns: {cell_id: {dcri, breakdown, trend}}
        """
        if not cell_type_counts:
            return {}

        # Find max counts per type for normalisation
        type_maxes = defaultdict(float)
        for cell, types in cell_type_counts.items():
            for t, count in types.items():
                type_maxes[t] = max(type_maxes[t], count)

        results = {}
        for cell, types in cell_type_counts.items():
            score = 0.0
            breakdown = {}
            for event_type, weight in self.WEIGHTS.items():
                count = types.get(event_type, 0)
                max_val = type_maxes.get(event_type, 1)
                normalised = (count / max_val) * 100 if max_val > 0 else 0
                component = normalised * weight
                score += component
                breakdown[event_type] = float(round(normalised, 1))

            # Add forecast delta (capped at ±10 points)
            delta = 0
            if forecast_deltas and cell in forecast_deltas:
                delta = max(-10, min(10, forecast_deltas[cell]))
                score += delta

            score = max(0, min(100, score))
            results[cell] = {
                "dcri": float(round(score, 1)),
                "breakdown": breakdown,
                "trend": "rising" if delta > 1 else "falling" if delta < -1 else "stable",
            }

        return results


# ============================================================================
# FORECAST ENGINE (Exponential Smoothing)
# ============================================================================

class ForecastEngine:
    """
    Per-cell time-series forecasting using simple exponential smoothing.
    Phase 1 fallback for the full ST-GNN / Prophet pipeline.
    """

    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha

    def forecast(self, daily_counts: list, horizon_days: int = 7) -> dict:
        """
        daily_counts: list of daily event counts (oldest → newest)
        horizon_days: how many days to forecast forward
        Returns: {historical, forecast, trend_delta}
        """
        if not daily_counts:
            return {"historical": [], "forecast": [0] * horizon_days, "trend_delta": 0}

        # Simple exponential smoothing
        smoothed = [daily_counts[0]]
        for i in range(1, len(daily_counts)):
            s = self.alpha * daily_counts[i] + (1 - self.alpha) * smoothed[-1]
            smoothed.append(round(s, 2))

        last_val = smoothed[-1]
        # Forecast = last smoothed value (flat forecast for SES)
        # Add slight trend from last 7 days
        recent = daily_counts[-min(7, len(daily_counts)):]
        if len(recent) >= 2:
            trend = (recent[-1] - recent[0]) / len(recent)
        else:
            trend = 0

        forecast_values = []
        for d in range(1, horizon_days + 1):
            pred = max(0, round(last_val + trend * d, 2))
            forecast_values.append(pred)

        trend_delta = round(forecast_values[-1] - daily_counts[-1], 2) if daily_counts else 0

        return {
            "historical": daily_counts,
            "smoothed": smoothed,
            "forecast": forecast_values,
            "trend_delta": trend_delta,
        }


# ============================================================================
# PATROL ALLOCATOR
# ============================================================================

class PatrolAllocator:
    """
    Ranks H3 cells by DCRI × (1 - patrol_coverage) for deployment recommendations.
    patrol_coverage defaults to 0 (no patrol) if not supplied.
    """

    def allocate(self, dcri_scores: dict, patrol_coverage: Optional[dict] = None, top_n: int = 10) -> list:
        """
        dcri_scores: {cell_id: {dcri: float, ...}}
        patrol_coverage: {cell_id: 0.0-1.0}
        Returns: sorted list of allocation recommendations
        """
        if not dcri_scores:
            return []

        if patrol_coverage is None:
            patrol_coverage = {}

        ranked = []
        for cell, data in dcri_scores.items():
            dcri = data.get("dcri", 0)
            coverage = patrol_coverage.get(cell, 0.0)
            priority = dcri * (1 - coverage)
            ranked.append({
                "cell_id": cell,
                "dcri": dcri,
                "patrol_coverage": round(coverage, 2),
                "priority_score": round(priority, 1),
                "trend": data.get("trend", "stable"),
                "recommendation": "CRITICAL DEPLOY" if priority > 70 else "HIGH PRIORITY" if priority > 40 else "MONITOR",
            })

        ranked.sort(key=lambda x: x["priority_score"], reverse=True)
        return ranked[:top_n]


# ============================================================================
# COMPOSITE GCPI PIPELINE
# ============================================================================

class GCPIPipeline:
    """
    Orchestrates the full GCPI analytics pipeline:
    1. Index events → H3 cells
    2. Aggregate counts per cell per type
    3. Compute Gi* hotspot statistics
    4. Detect emerging clusters (Kulldorff)
    5. Compute DCRI fusion scores
    6. Generate forecasts
    7. Rank patrol allocation
    """

    def __init__(self, resolution: int = 8):
        self.indexer = H3Indexer(resolution)
        self.gi_star = GiStarCalculator(self.indexer, k=1)
        self.clusterer = HDBSCANClusterer()
        self.scanner = KulldorffScanner(self.indexer)
        self.dcri_calc = DCRICalculator()
        self.forecaster = ForecastEngine()
        self.patrol = PatrolAllocator()
        self.resolution = resolution

    def run_full_pipeline(self, geo_events: list, days: int = 30) -> dict:
        """
        geo_events: list of dicts with keys: lat, lng, event_type, timestamp, severity, district, source_module, id, entity_refs_json
        Returns comprehensive GCPI analytics result.
        """
        if not geo_events:
            return {
                "hexgrid": [], "hotspots": [], "emerging_clusters": [],
                "dcri_scores": {}, "patrol_allocation": [], "stats": {},
                "forecast": {}
            }

        # 1. Index events into H3 cells
        cell_events = defaultdict(list)
        cell_type_counts = defaultdict(lambda: defaultdict(int))
        cell_daily = defaultdict(lambda: defaultdict(int))

        now = datetime.utcnow()
        cutoff = now - timedelta(days=days)

        for ev in geo_events:
            if ev.get("lat") is None or ev.get("lng") is None:
                continue
            ts = ev.get("timestamp", now)
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except Exception:
                    ts = now

            cell_id = self.indexer.latlng_to_cell(ev["lat"], ev["lng"])
            cell_events[cell_id].append(ev)
            cell_type_counts[cell_id][ev.get("event_type", "complaint")] += 1

            # Daily counts for forecasting
            day_key = (ts - cutoff).days
            if 0 <= day_key < days:
                cell_daily[cell_id][day_key] += 1

        # 2. Total counts per cell
        cell_counts = {c: len(evs) for c, evs in cell_events.items()}

        # 3. Gi* hotspot statistics
        gi_results = self.gi_star.compute(cell_counts)

        # 4. HDBSCAN clustering
        if len(cell_events) >= 3:
            coords = []
            coord_cells = []
            for cell_id in cell_events:
                center = self.indexer.cell_to_latlng(cell_id)
                coords.append([center[0], center[1]])
                coord_cells.append(cell_id)
            coords_arr = np.array(coords)
            cluster_labels = self.clusterer.cluster(coords_arr)
        else:
            cluster_labels = np.array([])
            coord_cells = []

        # 5. Emerging clusters (Kulldorff)
        emerging = self.scanner.scan(cell_counts)

        # 6. Forecasts per cell (top cells by count)
        top_cells = sorted(cell_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        forecast_deltas = {}
        forecast_data = {}
        for cell_id, count in top_cells:
            daily = cell_daily.get(cell_id, {})
            daily_series = [daily.get(d, 0) for d in range(days)]
            fc = self.forecaster.forecast(daily_series, horizon_days=7)
            forecast_deltas[cell_id] = fc["trend_delta"]
            forecast_data[cell_id] = fc

        # 7. DCRI computation
        dcri_scores = self.dcri_calc.compute(dict(cell_type_counts), forecast_deltas)

        # 8. Patrol allocation
        patrol_alloc = self.patrol.allocate(dcri_scores, top_n=15)

        # 8b. Enrich patrol entries with district names, coords & unit counts
        for entry in patrol_alloc:
            cid = entry["cell_id"]
            if cid in cell_events:
                districts = [e.get("district", "Unknown") for e in cell_events[cid]]
                entry["district"] = Counter(districts).most_common(1)[0][0] if districts else "Unknown"
            else:
                entry["district"] = "Unknown"
            center = self.indexer.cell_to_latlng(cid)
            entry["center_lat"] = round(center[0], 4)
            entry["center_lng"] = round(center[1], 4)
            # Recommended units: ceil(priority_score / 25), clamped 1-5
            entry["recommended_units"] = max(1, min(5, math.ceil(entry.get("priority_score", 0) / 25)))

        # 9. Build hexgrid response
        hexgrid = []
        for cell_id, events in cell_events.items():
            center = self.indexer.cell_to_latlng(cell_id)
            boundary = self.indexer.cell_to_boundary(cell_id)
            gi = gi_results.get(cell_id, {})
            dcri = dcri_scores.get(cell_id, {"dcri": 0, "breakdown": {}, "trend": "stable"})
            types = dict(cell_type_counts[cell_id])
            districts = [e.get("district", "Unknown") for e in events]
            primary_district = Counter(districts).most_common(1)[0][0] if districts else "Unknown"

            hexgrid.append({
                "cell_id": cell_id,
                "center_lat": round(center[0], 4),
                "center_lng": round(center[1], 4),
                "boundary": boundary,
                "event_count": len(events),
                "type_breakdown": types,
                "dcri": dcri["dcri"],
                "dcri_breakdown": dcri.get("breakdown", {}),
                "trend": dcri.get("trend", "stable"),
                "gi_z_score": gi.get("z_score", 0),
                "is_hotspot": gi.get("is_hot", False),
                "is_coldspot": gi.get("is_cold", False),
                "district": primary_district,
            })

        # 10. Stats summary
        total_events = sum(cell_counts.values())
        hot_count = sum(1 for g in gi_results.values() if g.get("is_hot"))
        top_dcri_cell = max(dcri_scores.items(), key=lambda x: x[1]["dcri"])[0] if dcri_scores else None
        top_dcri_district = None
        if top_dcri_cell and top_dcri_cell in cell_events:
            districts = [e.get("district") for e in cell_events[top_dcri_cell]]
            top_dcri_district = Counter(districts).most_common(1)[0][0] if districts else None

        stats = {
            "total_events": total_events,
            "active_cells": len(cell_events),
            "hotspot_cells": hot_count,
            "emerging_clusters": len(emerging),
            "top_dcri_district": top_dcri_district,
            "avg_dcri": round(np.mean([d["dcri"] for d in dcri_scores.values()]), 1) if dcri_scores else 0,
            "max_dcri": round(max(d["dcri"] for d in dcri_scores.values()), 1) if dcri_scores else 0,
        }

        return {
            "hexgrid": sorted(hexgrid, key=lambda x: x["dcri"], reverse=True),
            "hotspots": [h for h in hexgrid if h["is_hotspot"]],
            "emerging_clusters": emerging,
            "dcri_scores": {c: d for c, d in dcri_scores.items()},
            "patrol_allocation": patrol_alloc,
            "stats": stats,
            "forecast": forecast_data,
        }
