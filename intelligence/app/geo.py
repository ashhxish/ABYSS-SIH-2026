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
from typing import List, Optional, Sequence, Tuple

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
    "point_in_ring",
    "distance_to_ring_km",
    "convex_hull",
    "polygon_area_km2",
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


# ---------------------------------------------------------------------------
# Polygon helpers used by the origin-region hindcast and the compatibility
# filter. Both take rings as sequences of (lon, lat) pairs, matching GeoJSON
# coordinate order, and tolerate a duplicated closing point.
# ---------------------------------------------------------------------------
def point_in_ring(lon: float, lat: float, ring: Sequence[Tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test against a simple ring of (lon, lat).

    A closing duplicate (first == last) is ignored. Exact-boundary results are
    implementation-defined - the classic ray-casting caveat - which is why the
    compatibility filter combines this test with `distance_to_ring_km` and a
    small positional buffer rather than relying on either alone.
    """
    pts = [(float(p[0]), float(p[1])) for p in ring]
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return False
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > lat) != (yj > lat):
            x_cross = xj + (lat - yj) * (xi - xj) / (yj - yi)
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def _point_segment_distance_km(px: float, py: float, ax: float, ay: float,
                                bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    if span <= 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / span
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def distance_to_ring_km(lat: float, lon: float, ring: Sequence[Tuple[float, float]]) -> float:
    """Shortest distance in kilometres from a position to the EDGES of a ring.

    The ring is projected into a local flat frame centred on the query point
    (spherical Earth, equirectangular projection). At demo scale - tens to
    hundreds of kilometres - projection error is far below the prototype's
    uncertainty radii. An empty or degenerate ring returns +inf so that callers
    cannot mistake "no region" for "on the region".
    """
    pts = [(float(p[0]), float(p[1])) for p in ring]  # (lon, lat)
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return math.inf
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)

    def to_km(p: Tuple[float, float]) -> Tuple[float, float]:
        x = math.radians(p[0] - lon) * EARTH_RADIUS_KM * cos_lat
        y = math.radians(p[1] - lat) * EARTH_RADIUS_KM
        return (x, y)

    km_pts = [to_km(p) for p in pts]
    best = math.inf
    for i in range(len(km_pts)):
        ax, ay = km_pts[i]
        bx, by = km_pts[(i + 1) % len(km_pts)]
        best = min(best, _point_segment_distance_km(0.0, 0.0, ax, ay, bx, by))
    return best


def convex_hull(points: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Strict convex hull (Andrew's monotone chain) of (x, y) pairs.

    Returns a CLOSED ring (first point repeated at the end) in counter-clockwise
    order for distinct inputs; two or fewer distinct points are returned as-is
    (a degenerate "hull" callers should reject). Collinear points are dropped so
    the ring stays strictly convex - useful as a GeoJSON region boundary.
    """
    pts = sorted({(float(x), float(y)) for x, y in points})
    if len(pts) <= 2:
        return list(pts)

    def cross(o, a, b) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[Tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0.0:
            lower.pop()
        lower.append(p)
    upper: List[Tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0.0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return hull + [hull[0]]


def polygon_area_km2(ring: Sequence[Tuple[float, float]]) -> float:
    """Shoelace area in square kilometres of a closed [(lat, lon), ...] ring.

    Positions are projected into a local flat frame at the ring's mean latitude.
    Returns 0.0 for degenerate rings (fewer than three distinct vertices).
    """
    pts = [(float(p[1]), float(p[0])) for p in ring]  # -> (lat, lon)
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return 0.0
    ref_lat = sum(p[0] for p in pts) / len(pts)
    cos_lat = max(math.cos(math.radians(ref_lat)), 1e-6)

    def to_km(p):
        return (math.radians(p[1]) * EARTH_RADIUS_KM * cos_lat,
                math.radians(p[0]) * EARTH_RADIUS_KM)

    km_pts = [to_km(p) for p in pts]
    total = 0.0
    for i in range(len(km_pts)):
        x1, y1 = km_pts[i]
        x2, y2 = km_pts[(i + 1) % len(km_pts)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0
