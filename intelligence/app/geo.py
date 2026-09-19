"""ABYSS - geodesy helpers shared by the intelligence service.

WHY THIS EXISTS
    Trajectory construction (Phase 4), spatial compatibility (Phase 5) and the
    hindcast (Phase 11) all need the same distance maths. Keeping one reviewed
    implementation avoids three subtly different definitions of "distance".

WHAT IT IS NOT
    It is a prototype toolkit, not a geodesy library. Distances use the
    great-circle (haversine) formula on a spherical Earth; where a flat-earth
    offset is used it is documented and only applied at demo scale. Production
    work would consider an ellipsoidal model (see docs/methodology.md).

NOTE ON INDEPENDENCE
    The Phase 2 demo generator and the Phase 2 dataset tests deliberately keep
    their OWN copies of these formulas, so that a fault in this module cannot
    silently validate itself. Phases 3+ use this shared implementation.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

EARTH_RADIUS_KM = 6371.0088
KNOTS_TO_KMH = 1.852
M_PER_DEG_LAT = 111320.0

__all__ = [
    "EARTH_RADIUS_KM",
    "KNOTS_TO_KMH",
    "M_PER_DEG_LAT",
    "haversine_km",
    "initial_bearing_deg",
    "metres_per_degree_lon",
    "offset_position",
    "knots_to_kmh",
    "kmh_to_knots",
    "implied_speed_kn",
    "validate_coordinate",
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two WGS84 positions."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle course in degrees clockwise from true north (0-360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def metres_per_degree_lon(lat: float) -> float:
    """Approximate east-west metres per degree of longitude at a latitude."""
    return M_PER_DEG_LAT * math.cos(math.radians(lat))


def offset_position(lat: float, lon: float, bearing_deg: float, distance_km: float) -> Tuple[float, float]:
    """Flat-earth offset from a position. Adequate at demo scale and reproducible."""
    br = math.radians(bearing_deg)
    d_m = distance_km * 1000.0
    return (
        lat + (d_m * math.cos(br)) / M_PER_DEG_LAT,
        lon + (d_m * math.sin(br)) / metres_per_degree_lon(lat),
    )


def knots_to_kmh(knots: float) -> float:
    return knots * KNOTS_TO_KMH


def kmh_to_knots(kmh: float) -> float:
    return kmh / KNOTS_TO_KMH


def implied_speed_kn(distance_km: float, elapsed_seconds: float) -> Optional[float]:
    """Speed in knots implied by covering `distance_km` in `elapsed_seconds`.

    Returns None when the elapsed time is not positive, because no speed can be
    inferred from two records that share a timestamp. Callers must treat that as
    "unknown", never as "fast" or "slow".
    """
    if elapsed_seconds <= 0:
        return None
    return kmh_to_knots(distance_km / (elapsed_seconds / 3600.0))


def validate_coordinate(lat: float, lon: float, null_island_tolerance_deg: float = 1e-6) -> Optional[str]:
    """Return a human-readable problem description, or None when the position is usable."""
    if not math.isfinite(lat) or not math.isfinite(lon):
        return "non-finite coordinate"
    if not (-90.0 <= lat <= 90.0):
        return f"latitude {lat} outside [-90, 90]"
    if not (-180.0 <= lon <= 180.0):
        return f"longitude {lon} outside [-180, 180]"
    if abs(lat) <= null_island_tolerance_deg and abs(lon) <= null_island_tolerance_deg:
        return "null island position (0, 0), a classic receiver or parsing artefact"
    return None
