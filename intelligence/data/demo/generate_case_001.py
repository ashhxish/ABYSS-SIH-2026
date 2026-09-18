#!/usr/bin/env python3
"""
ABYSS - CASE-001 deterministic demonstration dataset generator (Phase 2).

WHAT THIS SCRIPT PRODUCES
    The complete synthetic demonstration dataset for the ABYSS oil-spill
    attribution prototype:
      * a 72-hour, 12-vessel synthetic AIS extract (CSV)
      * the observed oil-slick polygon of the demonstration scenario
      * a deterministic environmental current + wind field
      * the CASE-001 investigation configuration
      * test fixtures used by later phases (expected origin, expected ordering,
        injected data defects)
      * a manifest with SHA-256 hashes so reproducibility can be proven

WHAT THIS SCRIPT DELIBERATELY DOES NOT DO (later phases own these)
    No AIS cleaning, no trajectory construction, no spatial / temporal /
    trajectory filtering, no behaviour analysis, no AIS gap analysis, no
    evidence scoring, no backend, no database, no frontend. Nothing here ranks
    or accuses any vessel.

SCIENTIFIC HONESTY
    Every value is synthetic. No real vessel, voyage, spill or incident is
    described. Nothing in this dataset asserts that any vessel caused an oil
    spill; the data exists so the future forensic engine can be tested against a
    scenario whose intent is known in advance.

DETERMINISM
    No random number generator and no wall-clock time is used. Every value
    follows from arithmetic over fixed constants, so repeated runs are
    byte-identical (verified by intelligence/tests/test_case_001_dataset.py).

USAGE
    python3 intelligence/data/demo/generate_case_001.py
    python3 intelligence/data/demo/generate_case_001.py --out-dir /tmp/case_001
    python3 intelligence/data/demo/generate_case_001.py --quiet
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ===========================================================================
# 1. Scenario constants
# ===========================================================================
GENERATOR_VERSION = "1.0.0"
DATASET_LABEL = "Synthetic Demonstration Dataset"
DISCLAIMER = (
    "ABYSS provides analytical evidence for investigation support. Candidate ranking does "
    "not establish legal responsibility. This dataset is synthetic: it does not describe "
    "any real vessel, voyage, spill or incident, and nothing in it asserts that any vessel "
    "caused an oil spill."
)
UTC = timezone.utc

CASE_ID = "CASE-001"
SPILL_ID = "SPILL-001"

TRACK_START = datetime(2026, 3, 11, 6, 0, 0, tzinfo=UTC)
TRACK_HOURS = 72.0
OBSERVATION_TIME = TRACK_START + timedelta(hours=TRACK_HOURS)  # 2026-03-14T06:00:00Z

RELEASE_WINDOW_START = datetime(2026, 3, 13, 10, 0, 0, tzinfo=UTC)
RELEASE_WINDOW_END = datetime(2026, 3, 13, 18, 0, 0, tzinfo=UTC)
NOMINAL_RELEASE_TIME = datetime(2026, 3, 13, 14, 0, 0, tzinfo=UTC)

# Synthetic centre of the probable-origin uncertainty region. This is the
# scenario's true release point: a TEST FIXTURE value that is never presented to
# an investigator as an answer (see docs/methodology.md).
ORIGIN_CENTER: Tuple[float, float] = (18.30, 71.90)
ORIGIN_UNCERTAINTY_SEMI_MAJOR_KM = 10.0
ORIGIN_UNCERTAINTY_SEMI_MINOR_KM = 6.0
ORIGIN_UNCERTAINTY_BEARING_DEG = 50.0

# Observed slick shape (elongated along the drift axis) - prototype geometry.
SLICK_SEMI_MAJOR_KM = 6.0
SLICK_SEMI_MINOR_KM = 2.2
SLICK_BEARING_DEG = 52.0
DETECTION_CONFIDENCE = 0.91

# Area covered by the synthetic AIS extract (area-scoped query over the study area).
STUDY_BBOX = {"minLat": 16.5, "maxLat": 20.0, "minLon": 69.5, "maxLon": 74.5}

# Synthetic coastline used ONLY as land/sea plausibility context. It is a coarse
# approximation for the synthetic scenario and is not survey data.
SYNTHETIC_COASTLINE: List[List[float]] = [
    [72.35, 20.00],
    [72.62, 19.30],
    [72.85, 18.60],
    [73.22, 17.90],
    [73.55, 17.20],
    [73.80, 16.50],
]

M_PER_DEG_LAT = 111320.0
KNOT_TO_KMH = 1.852

# Windage coefficient: PROTOTYPE value, configurable, NOT scientifically
# validated (see docs/methodology.md section 4).
WINDAGE_COEFFICIENT = 0.03

# Deterministic modulation so reported values are not artificially perfect.
SOG_MOD_AMPLITUDE = 0.020
SOG_MOD_PERIOD_H = 6.0
COURSE_MOD_AMPLITUDE = 0.6
COURSE_MOD_PERIOD_H = 4.0

# --- deterministic environmental field parameters (prototype) ---
WIND_SPEED_MS = 8.0
WIND_FROM_DEG = 225.0  # meteorological convention: the wind blows FROM this bearing
CURRENT_BASE_U = 0.32
CURRENT_BASE_V = 0.20
CURRENT_AMP_U = 0.06
CURRENT_AMP_V = 0.05
CURRENT_WAVELENGTH_DEG = 3.0
CURRENT_LAT_REF = 17.0
CURRENT_LON_REF = 71.0
GRID_LAT_MIN, GRID_LAT_MAX, GRID_LAT_STEP = 17.5, 19.5, 0.25
GRID_LON_MIN, GRID_LON_MAX, GRID_LON_STEP = 70.5, 73.5, 0.25
DRIFT_STEP_SECONDS = 300.0
FIELD_TIME_BEHAVIOUR = "steady (prototype simplification: no temporal variation in this demo field)"

# ===========================================================================
# 2. Time, geodesy and geometry helpers
# ===========================================================================
def iso_z(dt: datetime) -> str:
    """ISO-8601 UTC timestamp with a trailing Z, second precision."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def hours_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600.0


def metres_per_deg_lon(lat: float) -> float:
    return M_PER_DEG_LAT * math.cos(math.radians(lat))


def offset_position(lat: float, lon: float, bearing_deg: float, distance_km: float) -> Tuple[float, float]:
    """Equirectangular offset. Deliberately simple and exactly reproducible.

    Production code (Phase 5+) uses geodesic calculations with explicit
    approximations documented; this generator only needs determinism at demo scale.
    """
    br = math.radians(bearing_deg)
    d_m = distance_km * 1000.0
    return (
        lat + (d_m * math.cos(br)) / M_PER_DEG_LAT,
        lon + (d_m * math.sin(br)) / metres_per_deg_lon(lat),
    )


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    mlon = metres_per_deg_lon((lat1 + lat2) / 2.0)
    east = (lon2 - lon1) * mlon
    north = (lat2 - lat1) * M_PER_DEG_LAT
    return (math.degrees(math.atan2(east, north)) + 360.0) % 360.0


def ellipse_ring(
    lat: float, lon: float, semi_major_km: float, semi_minor_km: float,
    bearing: float, vertices: int = 48,
) -> List[List[float]]:
    """GeoJSON closing ring ([lon, lat]) of an ellipse with its major axis on `bearing`."""
    br = math.radians(bearing)
    sin_b, cos_b = math.sin(br), math.cos(br)
    mlon = metres_per_deg_lon(lat)
    ring: List[List[float]] = []
    for i in range(vertices):
        theta = 2.0 * math.pi * i / vertices
        along = semi_major_km * 1000.0 * math.cos(theta)   # major axis (bearing)
        across = semi_minor_km * 1000.0 * math.sin(theta)  # minor axis (perpendicular)
        east = along * sin_b + across * cos_b
        north = along * cos_b - across * sin_b
        ring.append([round(lon + east / mlon, 6), round(lat + north / M_PER_DEG_LAT, 6)])
    ring.append(list(ring[0]))
    return ring


def ring_area_km2(ring: List[List[float]]) -> float:
    """Planar (equirectangular) shoelace area in km^2 - adequate at demo scale."""
    ref_lat = sum(p[1] for p in ring) / len(ring)
    mlon = metres_per_deg_lon(ref_lat)
    pts = [(p[0] * mlon, p[1] * M_PER_DEG_LAT) for p in ring]
    acc = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2.0 / 1_000_000.0


def ring_perimeter_km(ring: List[List[float]]) -> float:
    total = 0.0
    for i in range(len(ring) - 1):
        total += haversine_km(ring[i][1], ring[i][0], ring[i + 1][1], ring[i + 1][0])
    return total


def ring_bounds(ring: List[List[float]]) -> Dict[str, float]:
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return {"minLat": min(lats), "maxLat": max(lats), "minLon": min(lons), "maxLon": max(lons)}


def point_in_ring(lon: float, lat: float, ring: Sequence[Sequence[float]]) -> bool:
    """Ray casting test.

    FIXTURE VALIDATION ONLY. This is used by the generator and the dataset tests to
    confirm that the scenario was built as intended. The product's spatial
    compatibility filter is Phase 5 and must not depend on this helper.
    """
    inside = False
    pts = list(ring)
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i][0], pts[i][1]
        x2, y2 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            x_cross = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_cross:
                inside = not inside
    return inside


def round_floats(value: Any, ndigits: int = 6) -> Any:
    """Recursively round floats so JSON output is byte-stable across machines."""
    if isinstance(value, float):
        out = round(value, ndigits)
        return 0.0 if out == 0 else out
    if isinstance(value, dict):
        return {k: round_floats(v, ndigits) for k, v in value.items()}
    if isinstance(value, list):
        return [round_floats(v, ndigits) for v in value]
    if isinstance(value, tuple):
        return [round_floats(v, ndigits) for v in value]
    return value

# ===========================================================================
# 3. Deterministic environmental field (prototype definition)
# ===========================================================================
def wind_components() -> Tuple[float, float]:
    """Wind vector (east, north) in m/s derived from speed and 'from' direction."""
    motion_bearing = math.radians((WIND_FROM_DEG + 180.0) % 360.0)
    return (WIND_SPEED_MS * math.sin(motion_bearing), WIND_SPEED_MS * math.cos(motion_bearing))


def current_components(lat: float, lon: float) -> Tuple[float, float]:
    """Weak smooth spatial variation so the demo field is not perfectly uniform."""
    phase_lat = 2.0 * math.pi * (lat - CURRENT_LAT_REF) / CURRENT_WAVELENGTH_DEG
    phase_lon = 2.0 * math.pi * (lon - CURRENT_LON_REF) / CURRENT_WAVELENGTH_DEG
    u = CURRENT_BASE_U + CURRENT_AMP_U * math.sin(phase_lat) * math.cos(phase_lon)
    v = CURRENT_BASE_V + CURRENT_AMP_V * math.cos(phase_lat)
    return (u, v)


def drift_velocity(lat: float, lon: float) -> Tuple[float, float]:
    """Surface drift = surface current + windage * wind (prototype parametrisation)."""
    cu, cv = current_components(lat, lon)
    wu, wv = wind_components()
    return (cu + WINDAGE_COEFFICIENT * wu, cv + WINDAGE_COEFFICIENT * wv)


def integrate_drift(
    lat: float, lon: float, hours: float,
    step_seconds: float = DRIFT_STEP_SECONDS, sample_every_hours: float = 0.5,
) -> List[Tuple[float, float, float]]:
    """Forward Euler integration of the drift field.

    Returns [(hours_elapsed, lat, lon), ...]. This is a prototype explicit scheme
    with a fixed step; it is NOT a validated ocean model (see docs/methodology.md).
    """
    steps = int(round(hours * 3600.0 / step_seconds))
    sample_every = max(1, int(round(sample_every_hours * 3600.0 / step_seconds)))
    samples: List[Tuple[float, float, float]] = [(0.0, lat, lon)]
    for i in range(1, steps + 1):
        u, v = drift_velocity(lat, lon)
        lat = lat + (v * step_seconds) / M_PER_DEG_LAT
        lon = lon + (u * step_seconds) / metres_per_deg_lon(lat)
        if i % sample_every == 0 or i == steps:
            samples.append((i * step_seconds / 3600.0, lat, lon))
    return samples


def environmental_field() -> Dict[str, Any]:
    """Steady current + wind field sampled on a coarse regular grid."""
    n_lat = int(round((GRID_LAT_MAX - GRID_LAT_MIN) / GRID_LAT_STEP)) + 1
    n_lon = int(round((GRID_LON_MAX - GRID_LON_MIN) / GRID_LON_STEP)) + 1
    lats = [round(GRID_LAT_MIN + i * GRID_LAT_STEP, 6) for i in range(n_lat)]
    lons = [round(GRID_LON_MIN + i * GRID_LON_STEP, 6) for i in range(n_lon)]
    wu, wv = wind_components()
    wind_speed = math.hypot(wu, wv)
    # Meteorological convention: the direction the wind blows FROM.
    from_deg = (math.degrees(math.atan2(-wu, -wv)) + 360.0) % 360.0
    nodes: List[Dict[str, float]] = []
    for la in lats:
        for lo in lons:
            cu, cv = current_components(la, lo)
            nodes.append({
                "lat": la,
                "lon": lo,
                "uCurrent": round(cu, 6),
                "vCurrent": round(cv, 6),
                "uWind": round(wu, 6),
                "vWind": round(wv, 6),
                "windSpeed": round(wind_speed, 6),
                "windDirection": round(from_deg, 3),
            })
    return {
        "synthetic": True,
        "datasetLabel": DATASET_LABEL,
        "provider": "DemoEnvironmentalProvider",
        "uiLabel": "DEMO DATA",
        "validFrom": iso_z(TRACK_START),
        "validTo": iso_z(OBSERVATION_TIME),
        "timeBehaviour": FIELD_TIME_BEHAVIOUR,
        "units": {
            "uCurrent": "m/s (eastward)",
            "vCurrent": "m/s (northward)",
            "uWind": "m/s (eastward)",
            "vWind": "m/s (northward)",
            "windSpeed": "m/s",
            "windDirection": "degrees, meteorological convention (direction the wind blows FROM)",
        },
        "grid": {"latitudes": lats, "longitudes": lons, "nodeCount": len(nodes)},
        "nodes": nodes,
        "analyticDefinition": {
            "note": (
                "Coefficients of the synthetic demonstration field. They are prototype values "
                "chosen to make the scenario internally consistent; they are NOT calibrated "
                "scientific constants and must not be cited as such."
            ),
            "windSpeed": WIND_SPEED_MS,
            "windFromDirection": WIND_FROM_DEG,
            "currentBaseU": CURRENT_BASE_U,
            "currentBaseV": CURRENT_BASE_V,
            "currentAmplitudeU": CURRENT_AMP_U,
            "currentAmplitudeV": CURRENT_AMP_V,
            "currentWavelengthDeg": CURRENT_WAVELENGTH_DEG,
        },
        "windageCoefficient": WINDAGE_COEFFICIENT,
        "windageNote": "PROTOTYPE value, configurable, not scientifically validated.",
        "fallback": "This provider always succeeds: it is the demo fallback itself.",
    }


# ===========================================================================
# 4. Vessel and AIS record model
# ===========================================================================
@dataclass(frozen=True)
class Segment:
    """One phase of a synthetic track. kind='gap' emits no AIS records."""
    kind: str
    hours: float
    course_deg: float
    speed_kn: float
    nav_status: int = 0
    jump_km: float = 0.0
    jump_bearing_deg: float = 0.0
    label: str = ""


@dataclass(frozen=True)
class VesselSpec:
    vessel_id: str
    mmsi: str
    imo: str
    name: str
    type_code: int
    type_label: str
    role: str
    role_key: str
    role_description: str
    interval_s: int
    phase: float
    segments: Tuple[Segment, ...]
    anchor_hour: float
    anchor_ref: Tuple[Any, ...]
    expected: Dict[str, Any]


@dataclass
class AisRow:
    vessel_id: str
    mmsi: str
    imo: str
    vessel_name: str
    vessel_type: int
    timestamp: str
    lat: float
    lon: float
    sog: float
    cog: float
    heading: Optional[int]
    nav_status: Optional[int]
    seq: int
    hour: float
    sort_seconds: float
    segment_label: str
    defects: List[str] = field(default_factory=list)

    def to_csv(self) -> List[str]:
        return [
            self.mmsi,
            self.imo,
            self.vessel_name,
            str(self.vessel_type),
            self.timestamp,
            f"{self.lat:.6f}",
            f"{self.lon:.6f}",
            f"{self.sog:.1f}",
            f"{self.cog:.1f}",
            "" if self.heading is None else str(self.heading),
            "" if self.nav_status is None else str(self.nav_status),
            DATASET_LABEL,
        ]


CSV_COLUMNS = [
    "MMSI", "IMO", "vesselName", "vesselType", "timestamp", "latitude", "longitude",
    "SOG", "COG", "heading", "navigationStatus", "datasetLabel",
]


def synthetic_imo(seq: int) -> str:
    """Format-valid 7-digit IMO placeholder in the 9990xx block.

    The real IMO check-digit rule is applied so the field exercises validation
    logic, but the value is synthetic: ABYSS does not assert that it corresponds
    to any real vessel.
    """
    base = f"9990{seq:02d}"  # 6 digits
    weights = (7, 6, 5, 4, 3, 2)
    check = sum(int(d) * w for d, w in zip(base, weights)) % 10
    return f"{base}{check}"


def synthetic_mmsi(seq: int) -> str:
    """Synthetic 9-digit MMSI placeholder.

    The 900xxxxxx block is used as a clearly synthetic convention for this demo
    dataset; ABYSS makes no claim about MMSI allocation and these identifiers are
    not attributed to any real vessel.
    """
    return f"9000000{seq:02d}"

# ===========================================================================
# 5. Track construction (raw synthetic tracks, pre-clipping)
# ===========================================================================
def resolve_anchor(ref: Tuple[Any, ...], ctx: Dict[str, Tuple[float, float]]) -> Tuple[float, float]:
    """Resolve a vessel's anchor reference to a concrete (lat, lon)."""
    kind = ref[0]
    if kind == "origin":
        return ctx["origin"]
    if kind == "origin_offset":
        return offset_position(ctx["origin"][0], ctx["origin"][1], ref[1], ref[2])
    if kind == "slick_offset":
        return offset_position(ctx["slick"][0], ctx["slick"][1], ref[1], ref[2])
    raise ValueError(f"unknown anchor reference: {ref!r}")


def build_samples(spec: VesselSpec) -> List[Tuple[Any, ...]]:
    """Emit raw samples for one vessel over the full 72 h track.

    The track is built around an arbitrary working origin and translated onto the
    vessel's anchor afterwards, so later changes to the anchor cannot alter the
    shape of the trajectory.
    """
    lat, lon = 0.0, 0.0
    t = TRACK_START
    rows: List[Tuple[Any, ...]] = []
    for seg in spec.segments:
        steps = int(round(seg.hours * 3600.0 / spec.interval_s))
        for step_index in range(steps):
            hour = hours_between(TRACK_START, t)
            if seg.kind == "move":
                sog = seg.speed_kn * (
                    1.0 + SOG_MOD_AMPLITUDE * math.sin(2.0 * math.pi * hour / SOG_MOD_PERIOD_H + spec.phase)
                )
                cog = (
                    seg.course_deg
                    + COURSE_MOD_AMPLITUDE * math.sin(2.0 * math.pi * hour / COURSE_MOD_PERIOD_H + spec.phase)
                ) % 360.0
                rows.append((t, hour, lat, lon, sog, cog, seg.nav_status, seg.label))
                km = seg.speed_kn * KNOT_TO_KMH * (spec.interval_s / 3600.0)
                lat, lon = offset_position(lat, lon, seg.course_deg, km)
            else:
                # Gap: no records are emitted. The vessel keeps moving; for the
                # 'physically impossible' scenario variant an additional unphysical
                # jump is applied ONCE, on the final step of the gap, so the vessel
                # reappears far beyond what the elapsed time can explain.
                km = seg.speed_kn * KNOT_TO_KMH * (spec.interval_s / 3600.0)
                lat, lon = offset_position(lat, lon, seg.course_deg, km)
                if seg.jump_km and step_index == steps - 1:
                    lat, lon = offset_position(lat, lon, seg.jump_bearing_deg, seg.jump_km)
            t = t + timedelta(seconds=spec.interval_s)
    return rows


def translate_to_anchor(
    rows: List[Tuple[Any, ...]], anchor_hour: float, anchor_lat: float, anchor_lon: float,
) -> List[Tuple[Any, ...]]:
    """Shift the whole track so it passes exactly through the anchor position."""
    ref_index = len(rows) - 1
    for i, r in enumerate(rows):
        if r[1] >= anchor_hour:
            ref_index = i
            break
    if ref_index == 0:
        base_lat, base_lon = rows[0][2], rows[0][3]
    else:
        before, after = rows[ref_index - 1], rows[ref_index]
        span = after[1] - before[1]
        w = 0.0 if span == 0 else (anchor_hour - before[1]) / span
        base_lat = before[2] + (after[2] - before[2]) * w
        base_lon = before[3] + (after[3] - before[3]) * w
    dlat = anchor_lat - base_lat
    dlon = anchor_lon - base_lon
    return [(r[0], r[1], r[2] + dlat, r[3] + dlon, r[4], r[5], r[6], r[7]) for r in rows]


def in_study_bbox(lat: float, lon: float) -> bool:
    return (
        STUDY_BBOX["minLat"] <= lat <= STUDY_BBOX["maxLat"]
        and STUDY_BBOX["minLon"] <= lon <= STUDY_BBOX["maxLon"]
    )


def build_vessel_rows(spec: VesselSpec, ctx: Dict[str, Tuple[float, float]]) -> List[AisRow]:
    """Build one vessel's AIS rows, keeping only positions inside the study area.

    Clipping models an AREA-SCOPED AIS extract: positions outside the query box are
    simply not part of the extract. This is what gives some vessels their natural
    'start of extract' and 'end of extract' boundaries.
    """
    anchor_lat, anchor_lon = resolve_anchor(spec.anchor_ref, ctx)
    raw = translate_to_anchor(build_samples(spec), spec.anchor_hour, anchor_lat, anchor_lon)
    out: List[AisRow] = []
    seq = 0
    for (t, hour, lat, lon, sog, cog, nav, label) in raw:
        if not in_study_bbox(lat, lon):
            continue
        seq += 1
        # AIS course over ground is 0.0-359.9 degrees. Rounding must happen BEFORE the
        # wrap-around test, otherwise a course of 359.96 would be written as "360.0".
        cog_rounded = round(cog % 360.0, 1)
        if cog_rounded >= 360.0 or cog_rounded < 0.0:
            cog_rounded = 0.0
        out.append(AisRow(
            vessel_id=spec.vessel_id,
            mmsi=spec.mmsi,
            imo=spec.imo,
            vessel_name=spec.name,
            vessel_type=spec.type_code,
            timestamp=iso_z(t),
            lat=lat,
            lon=lon,
            sog=max(0.0, sog),
            cog=cog_rounded,
            heading=int(round(cog_rounded)) % 360,
            nav_status=nav,
            seq=seq,
            hour=hour,
            sort_seconds=t.timestamp(),
            segment_label=label,
        ))
    return out


def copy_row(row: AisRow, **changes: Any) -> AisRow:
    data: Dict[str, Any] = {
        "vessel_id": row.vessel_id, "mmsi": row.mmsi, "imo": row.imo,
        "vessel_name": row.vessel_name, "vessel_type": row.vessel_type,
        "timestamp": row.timestamp, "lat": row.lat, "lon": row.lon,
        "sog": row.sog, "cog": row.cog, "heading": row.heading,
        "nav_status": row.nav_status, "seq": row.seq, "hour": row.hour,
        "sort_seconds": row.sort_seconds, "segment_label": row.segment_label,
        "defects": list(row.defects),
    }
    data.update(changes)
    return AisRow(**data)


def _pick(rows: List[AisRow], fraction: float) -> AisRow:
    """Deterministically select a row by relative position in the vessel's track."""
    if not rows:
        raise ValueError("cannot select a row from an empty track")
    idx = int(round(fraction * (len(rows) - 1)))
    return rows[min(len(rows) - 1, max(0, idx))]


# ===========================================================================
# 6. Intentional, documented data-quality defects (Phase 3 targets)
# ===========================================================================
def inject_defects(rows_by_vessel: Dict[str, List[AisRow]]) -> List[Dict[str, Any]]:
    """Inject deterministic data-quality defects that Phase 3 cleaning must handle.

    Every injection is logged with a stable defect id so tests, the dataset README
    and the Phase 3 implementation can refer to exactly the same rows.
    """
    log: List[Dict[str, Any]] = []
    counter = {"n": 0}

    def record(vessel_id: str, category: str, description: str, **ident: Any) -> None:
        counter["n"] += 1
        entry: Dict[str, Any] = {
            "defectId": f"D{counter['n']:02d}",
            "vesselId": vessel_id,
            "category": category,
            "description": description,
        }
        entry.update(ident)
        log.append(entry)

    # --- 1. duplicate records (V007) --------------------------------------
    for i, fraction in enumerate((0.30, 0.45, 0.60, 0.75), start=1):
        src = _pick(rows_by_vessel["V007"], fraction)
        dup = copy_row(src, seq=src.seq + 1000 + i, defects=["duplicate_record"])
        rows_by_vessel["V007"].append(dup)
        record(
            "V007", "duplicate_record",
            "Exact duplicate of an existing record (same MMSI, timestamp and position).",
            mmsi=src.mmsi, timestampWritten=src.timestamp,
            latitude=round(src.lat, 6), longitude=round(src.lon, 6),
            expectedPhase3Action="reject as duplicate (counted and logged, never silently dropped)",
        )

    # --- 2. malformed timestamps (V008) -----------------------------------
    malformed = (
        (0.35, "2026-03-12T25:61:00Z", "invalid hour and minute fields"),
        (0.55, "12/03/2026 08:00", "non-ISO date format"),
    )
    for fraction, bad_value, label in malformed:
        row = _pick(rows_by_vessel["V008"], fraction)
        intended = row.timestamp
        row.timestamp = bad_value
        row.defects.append("malformed_timestamp")
        record(
            "V008", "malformed_timestamp",
            f"Timestamp is not a valid ISO-8601 UTC instant ({label}).",
            mmsi=row.mmsi, timestampWritten=bad_value, intendedTimestamp=intended,
            expectedPhase3Action="reject row as unparseable timestamp (counted and logged)",
        )

    # --- 3. out-of-range coordinates (V012, V010) -------------------------
    row = _pick(rows_by_vessel["V012"], 0.40)
    row.lat = 95.2
    row.defects.append("invalid_coordinate")
    record(
        "V012", "invalid_coordinate",
        "Latitude outside the valid range [-90, 90].",
        mmsi=row.mmsi, timestampWritten=row.timestamp, latitude=95.2,
        expectedPhase3Action="reject row (counted and logged)",
    )

    row = _pick(rows_by_vessel["V010"], 0.50)
    row.lat, row.lon = 0.0, 0.0
    row.defects.append("invalid_coordinate")
    record(
        "V010", "invalid_coordinate",
        "Null-island position (0, 0), a classic receiver/parsing artefact.",
        mmsi=row.mmsi, timestampWritten=row.timestamp, latitude=0.0, longitude=0.0,
        expectedPhase3Action="reject row (counted and logged)",
    )

    # --- 4. negative speed over ground (V006) -----------------------------
    row = _pick(rows_by_vessel["V006"], 0.30)
    row.sog = -3.0
    row.defects.append("negative_speed")
    record(
        "V006", "negative_speed",
        "Negative speed over ground is not physically meaningful.",
        mmsi=row.mmsi, timestampWritten=row.timestamp, sog=-3.0,
        expectedPhase3Action="reject value (counted and logged)",
    )

    # --- 5. impossible-speed jump (V006) ----------------------------------
    src = _pick(rows_by_vessel["V006"], 0.50)
    jump_lat, jump_lon = offset_position(src.lat, src.lon, 0.0, 60.0)
    jump = copy_row(
        src,
        lat=jump_lat,
        lon=jump_lon,
        timestamp=iso_z(datetime.fromtimestamp(src.sort_seconds, UTC) - timedelta(seconds=300)),
        sort_seconds=src.sort_seconds - 300.0,
        sog=12.0,
        seq=src.seq + 2000,
        defects=["impossible_speed_jump"],
    )
    rows_by_vessel["V006"].append(jump)
    record(
        "V006", "impossible_speed_jump",
        "Added record 60 km from the vessel's next position only 5 minutes earlier, implying "
        "~720 km/h. Because it teleports out and back it produces exactly TWO impossible "
        "consecutive steps, both attributable to this single injected row.",
        mmsi=jump.mmsi, timestampWritten=jump.timestamp,
        latitude=round(jump_lat, 6), longitude=round(jump_lon, 6), impliedSpeedKmh=720.0,
        expectedPhase3Action="reject as impossible speed for the elapsed time (counted and logged)",
    )

    # --- 6. missing optional fields (V011) --------------------------------
    for fraction in (0.25, 0.50, 0.75):
        row = _pick(rows_by_vessel["V011"], fraction)
        row.heading = None
        row.nav_status = None
        row.defects.append("missing_optional_field")
        record(
            "V011", "missing_optional_field",
            "Heading and navigation status absent (optional fields keep the row valid).",
            mmsi=row.mmsi, timestampWritten=row.timestamp,
            expectedPhase3Action="keep row, flag missing optional fields",
        )

    return log

# ===========================================================================
# 7. The twelve synthetic vessels
# ===========================================================================
# Each vessel exists to exercise ONE forensic behaviour. The design contract is
# documented in docs/demo-scenario.md; the roles deliberately include plausible
# candidates, distractors and control vessels. NONE of them is claimed to have
# caused a spill - the scenario only asks whose movement would be COMPATIBLE.
# ===========================================================================
def _spec_v001() -> VesselSpec:
    """V001 - plausible primary candidate (specification test case A).

    Approaches the probable-origin region, slows to ~1.5 kn and loiters INSIDE the
    uncertainty region during the release window (roughly 4.3 h inside the ellipse),
    then resumes transit. No AIS gap, so this is the evidence-rich candidate.
    """
    return VesselSpec(
        vessel_id="V001", mmsi=synthetic_mmsi(1), imo=synthetic_imo(1),
        name="DEMO MERIDIAN STAR", type_code=80, type_label="Tanker (synthetic demonstration vessel)",
        role="Primary plausible candidate", role_key="plausible_primary",
        role_description=(
            "Inside the probable-origin uncertainty region during the release window with a "
            "compatible trajectory and a marked slowdown nearby. Expected highest compatibility."
        ),
        interval_s=300, phase=0.35,
        segments=(
            Segment("move", 48.0, 50.0, 11.5, nav_status=0, label="transit_run_in"),
            Segment("move", 8.0, 50.0, 1.5, nav_status=1, label="slowdown_inside_origin_region"),
            Segment("move", 16.0, 50.0, 11.5, nav_status=0, label="transit_run_out"),
        ),
        anchor_hour=53.0, anchor_ref=("origin",),
        expected={
            "hypothesis": "spatially, temporally and trajectory compatible",
            "mapsToSpecCase": "A",
            "inOriginRegionDuringWindow": True,
            "hasAisGap": False,
            "expectedRankBand": "top-2",
            "notes": "Slowdown and loitering also have innocent explanations (see methodology).",
        },
    )


def _spec_v002() -> VesselSpec:
    """V002 - gap-compatible candidate (specification test case E).

    Nearly identical geometry to V003: it is inside the origin uncertainty region
    when a 4 h AIS transmission gap begins, and the gap spans the region. Unlike
    V003 the vessel reappears only ~78 km away, which is bridgeable at ~10.5 kn,
    so the gap IS physically compatible and should become relevant.
    """
    return VesselSpec(
        vessel_id="V002", mmsi=synthetic_mmsi(2), imo=synthetic_imo(2),
        name="DEMO CORAL VOYAGER", type_code=80, type_label="Tanker (synthetic demonstration vessel)",
        role="Gap-compatible candidate", role_key="plausible_gap_compatible",
        role_description=(
            "Inside the origin region when a 4 h AIS gap starts; the gap crosses the region and "
            "its endpoints are reachable at a plausible 10.5 kn. Expected high compatibility."
        ),
        interval_s=300, phase=1.10,
        segments=(
            Segment("move", 54.0, 50.0, 10.5, label="approach"),
            Segment("gap", 4.0, 50.0, 10.5, label="ais_gap_physically_compatible"),
            Segment("move", 14.0, 50.0, 10.5, label="departure"),
        ),
        anchor_hour=54.0, anchor_ref=("origin_offset", 230.0, 2.0),
        expected={
            "hypothesis": "AIS gap that is physically consistent with the origin region",
            "mapsToSpecCase": "E",
            "inOriginRegionDuringWindow": True,
            "hasAisGap": True,
            "gapDurationHours": 4.0,
            "gapStart": iso_z(TRACK_START + timedelta(hours=54)),
            "gapEnd": iso_z(TRACK_START + timedelta(hours=58)),
            "gapBridgesOriginRegion": True,
            "gapFeasible": True,
            "expectedImpliedSpeedKn": "~10.5 (feasible)",
            "expectedRankBand": "top-2",
            "notes": "Same anchor geometry as V003: the only difference is whether the gap is traversable.",
        },
    )


def _spec_v003() -> VesselSpec:
    """V003 - gap NOT physically compatible (specification test case D).

    Same story as V002 (inside the region when a 4 h gap starts; the gap spans the
    region) but the vessel reappears ~260 km away, requiring ~35 kn. The gap must
    therefore contribute almost nothing to its ranking.
    """
    return VesselSpec(
        vessel_id="V003", mmsi=synthetic_mmsi(3), imo=synthetic_imo(3),
        name="DEMO IRON HORIZON", type_code=80, type_label="Tanker (synthetic demonstration vessel)",
        role="Gap-impossible candidate", role_key="distractor_gap_impossible",
        role_description=(
            "Inside the origin region when a 4 h AIS gap starts, but reappears ~260 km away - "
            "an implied ~35 kn. The gap is physically impossible and must not raise suspicion."
        ),
        interval_s=300, phase=2.05,
        segments=(
            Segment("move", 54.0, 60.0, 12.0, label="approach"),
            Segment("gap", 4.0, 60.0, 12.0, jump_km=175.0, jump_bearing_deg=60.0,
                    label="ais_gap_physically_impossible"),
            Segment("move", 14.0, 60.0, 12.0, label="departure"),
        ),
        anchor_hour=54.0, anchor_ref=("origin_offset", 215.0, 4.0),
        expected={
            "hypothesis": "AIS gap that is NOT physically compatible with the origin region",
            "mapsToSpecCase": "D",
            "inOriginRegionDuringWindow": True,
            "hasAisGap": True,
            "gapDurationHours": 4.0,
            "gapStart": iso_z(TRACK_START + timedelta(hours=54)),
            "gapEnd": iso_z(TRACK_START + timedelta(hours=58)),
            "gapBridgesOriginRegion": True,
            "gapFeasible": False,
            "minImpliedSpeedKn": 30.0,
            "expectedRankBand": "top-3 but strictly below V002",
            "notes": (
                "Paired with V002 to prove that gap detection alone cannot drive the ranking: "
                "the difference is physical feasibility only."
            ),
        },
    )


def _spec_v004() -> VesselSpec:
    """V004 - misleading nearby vessel (specification test cases C and G).

    Comes north from far outside the study area and, by the observation time, is the
    CLOSEST vessel to the observed slick (~7 km) after a slow 2 kn loiter. During the
    release window however it is still 120+ km from the probable-origin region, so it
    must not rank first. This is the anti-'nearest vessel wins' guard.
    """
    return VesselSpec(
        vessel_id="V004", mmsi=synthetic_mmsi(4), imo=synthetic_imo(4),
        name="DEMO HARBOUR LIGHT", type_code=70, type_label="Cargo (synthetic demonstration vessel)",
        role="Misleading nearby vessel", role_key="distractor_nearest_to_slick",
        role_description=(
            "Closest vessel to the OBSERVED slick at observation time, but far from the probable "
            "ORIGIN during the release window. Distractor for proximity-based reasoning."
        ),
        interval_s=300, phase=0.80,
        segments=(
            Segment("move", 52.0, 0.0, 10.0, nav_status=0, label="northbound_transit"),
            Segment("move", 16.0, 0.0, 9.0, nav_status=0, label="northbound_transit"),
            Segment("move", 4.0, 30.0, 2.0, nav_status=0, label="slow_loiter_near_slick"),
        ),
        anchor_hour=72.0, anchor_ref=("slick_offset", 40.0, 7.0),
        expected={
            "hypothesis": "nearest to the observed slick but spatially incompatible with the origin",
            "mapsToSpecCase": "C and G",
            "inOriginRegionDuringWindow": False,
            "hasAisGap": False,
            "closestToSlickAtObservation": True,
            "minDistanceToOriginKmDuringWindow": 100.0,
            "expectedRankBand": "not first, not top-2",
            "notes": "A 2 kn loiter near the slick is a behavioural anomaly that must not outweigh location and time.",
        },
    )


def _spec_v005() -> VesselSpec:
    """V005 - temporally incompatible (specification test case B).

    Steams north-east on a constant track and passes exactly through the origin
    region centre, but only ~6 h AFTER the release window has closed, and it is
    120+ km away throughout the window itself.
    """
    return VesselSpec(
        vessel_id="V005", mmsi=synthetic_mmsi(5), imo=synthetic_imo(5),
        name="DEMO SILVER TIDE", type_code=70, type_label="Cargo (synthetic demonstration vessel)",
        role="Wrong-time vessel", role_key="distractor_wrong_time",
        role_description=(
            "Crosses the probable-origin region hours AFTER the release window closes. Correct "
            "place, wrong time: expected low temporal compatibility."
        ),
        interval_s=300, phase=1.70,
        segments=(Segment("move", 72.0, 45.0, 11.0, nav_status=0, label="steady_transit"),),
        anchor_hour=66.0, anchor_ref=("origin",),
        expected={
            "hypothesis": "spatially plausible but temporally incompatible",
            "mapsToSpecCase": "B",
            "inOriginRegionDuringWindow": False,
            "hasAisGap": False,
            "minDistanceToOriginKmDuringWindow": 100.0,
            "passesOriginAfterWindowHours": 6.0,
            "expectedRankBand": "below V001 and V002",
            "notes": "Tests that a model collapsing time would wrongly promote this vessel.",
        },
    )


def _spec_v006() -> VesselSpec:
    """V006 - anomalous but remote (specification test case F).

    A repeated 24 h manoeuvring loop far to the east with strongly varying speed
    (8 kn vs 3 kn) and frequent 90 degree course changes: a clear behavioural
    anomaly, but 200+ km from the origin region. Also carries two injected data
    defects (negative SOG, impossible-speed jump) for Phase 3.
    """
    cycle = (
        Segment("move", 3.0, 0.0, 8.0, nav_status=0, label="manoeuvre_east_course_000"),
        Segment("move", 3.0, 90.0, 8.0, nav_status=0, label="manoeuvre_east_course_090"),
        Segment("move", 3.0, 180.0, 8.0, nav_status=0, label="manoeuvre_east_course_180"),
        Segment("move", 3.0, 270.0, 8.0, nav_status=0, label="manoeuvre_east_course_270"),
        Segment("move", 3.0, 0.0, 3.0, nav_status=0, label="manoeuvre_slow_course_000"),
        Segment("move", 3.0, 90.0, 3.0, nav_status=0, label="manoeuvre_slow_course_090"),
        Segment("move", 3.0, 180.0, 3.0, nav_status=0, label="manoeuvre_slow_course_180"),
        Segment("move", 3.0, 270.0, 3.0, nav_status=0, label="manoeuvre_slow_course_270"),
    )
    return VesselSpec(
        vessel_id="V006", mmsi=synthetic_mmsi(6), imo=synthetic_imo(6),
        name="DEMO FROST PELICAN", type_code=70, type_label="Cargo (synthetic demonstration vessel)",
        role="Anomalous but remote", role_key="distractor_anomaly_without_location",
        role_description=(
            "Strong behavioural anomaly (speed swings and 90 degree course changes) ~200 km from "
            "the origin region. Anomaly alone must not produce a high rank."
        ),
        interval_s=600, phase=2.60,
        segments=cycle * 3,
        anchor_hour=56.0, anchor_ref=("origin_offset", 105.0, 220.0),
        expected={
            "hypothesis": "behavioural anomaly without spatial or temporal compatibility",
            "mapsToSpecCase": "F",
            "inOriginRegionDuringWindow": False,
            "hasAisGap": False,
            "minDistanceToOriginKmDuringWindow": 150.0,
            "speedVariabilityKn": "~5 (8 vs 3), plus injected defects",
            "expectedRankBand": "outside the top-5",
            "notes": "Also carries the negative-SOG and impossible-speed defect rows.",
        },
    )


def _spec_v007() -> VesselSpec:
    """V007 - control tanker on a legitimate corridor (no anomaly intended).

    Steady 12.5 kn on an eastward track about 90 km south of the origin region, so it
    is inside the study area during the release window but never spatially compatible.
    It also carries the four injected DUPLICATE records (Phase 3 fixture).
    """
    return VesselSpec(
        vessel_id="V007", mmsi=synthetic_mmsi(7), imo=synthetic_imo(7),
        name="DEMO NORTHERN GATE", type_code=80, type_label="Tanker (synthetic demonstration vessel)",
        role="Control vessel (steady transit)", role_key="control_steady_transit",
        role_description=(
            "Legitimate steady transit ~90 km from the origin region: no anomaly, no gap. Shows "
            "that a normal vessel in the same area and time window is not promoted."
        ),
        interval_s=300, phase=0.50,
        segments=(Segment("move", 72.0, 90.0, 12.5, nav_status=0, label="steady_corridor_transit"),),
        anchor_hour=56.0, anchor_ref=("origin_offset", 180.0, 90.0),
        expected={
            "hypothesis": "control: normal behaviour, insufficient spatial compatibility",
            "mapsToSpecCase": None,
            "inOriginRegionDuringWindow": False,
            "hasAisGap": False,
            "minDistanceToOriginKmDuringWindow": 50.0,
            "maxSpeedSpreadKn": 0.5,
            "expectedRankBand": "mid",
            "notes": "Carries the duplicate-record defect fixture.",
        },
    )


def _spec_v008() -> VesselSpec:
    """V008 - fishing-like vessel (legitimate slow behaviour, far from the origin).

    Repeats a 24 h working pattern with long slow periods (0.2 kn, status 1) and
    direction changes, roughly 170 km west of the origin region. Slow speed alone
    must not be treated as suspicious.
    """
    cycle = (
        Segment("move", 6.0, 40.0, 4.5, nav_status=0, label="working_run_northeast"),
        Segment("move", 3.0, 340.0, 1.6, nav_status=0, label="working_haul_back"),
        Segment("move", 4.0, 0.0, 0.2, nav_status=1, label="stationary_working_period"),
        Segment("move", 5.0, 220.0, 4.5, nav_status=0, label="working_run_southwest"),
        Segment("move", 3.0, 0.0, 0.2, nav_status=1, label="stationary_working_period"),
        Segment("move", 3.0, 130.0, 3.0, nav_status=0, label="working_run_southeast"),
    )
    return VesselSpec(
        vessel_id="V008", mmsi=synthetic_mmsi(8), imo=synthetic_imo(8),
        name="DEMO SEA LARK", type_code=30, type_label="Fishing (synthetic demonstration vessel)",
        role="Fishing-like distractor", role_key="distractor_fishing_pattern",
        role_description=(
            "Many slow and stationary periods and an irregular track, but ~170 km from the "
            "origin region. Legitimate working pattern that must not be flagged as suspicious."
        ),
        interval_s=600, phase=1.35,
        segments=cycle * 3,
        anchor_hour=56.0, anchor_ref=("origin_offset", 270.0, 172.0),
        expected={
            "hypothesis": "legitimate slow/looping pattern, spatially incompatible",
            "mapsToSpecCase": None,
            "inOriginRegionDuringWindow": False,
            "hasAisGap": False,
            "minDistanceToOriginKmDuringWindow": 100.0,
            "hasStationaryPeriods": True,
            "expectedRankBand": "low",
            "notes": "Carries the two malformed-timestamp defect fixtures.",
        },
    )


def _spec_v009() -> VesselSpec:
    """V009 - ferry on a fixed shuttle corridor (high speed is not suspicious).

    Runs 4 h legs east/west at a constant 19 kn about 110 km north of the origin
    region, turning 180 degrees at each end. The instant turnarounds are a
    simplification of the synthetic data and are documented as such.
    """
    legs = tuple(
        Segment("move", 4.0, 90.0 if i % 2 == 0 else 270.0, 19.0, nav_status=0,
                label="shuttle_leg_eastbound" if i % 2 == 0 else "shuttle_leg_westbound")
        for i in range(18)
    )
    return VesselSpec(
        vessel_id="V009", mmsi=synthetic_mmsi(9), imo=synthetic_imo(9),
        name="DEMO SKY BRIDGE", type_code=60, type_label="Passenger (synthetic demonstration vessel)",
        role="High-speed control", role_key="control_high_speed",
        role_description=(
            "Fast, steady, predictable shuttle service well north of the origin region. High "
            "speed and the 180 degree turnarounds must not be read as suspicious behaviour."
        ),
        interval_s=600, phase=0.15,
        segments=legs,
        anchor_hour=58.0, anchor_ref=("origin_offset", 0.0, 111.0),
        expected={
            "hypothesis": "control: high speed and turnarounds are not suspicious by themselves",
            "mapsToSpecCase": None,
            "inOriginRegionDuringWindow": False,
            "hasAisGap": False,
            "minDistanceToOriginKmDuringWindow": 50.0,
            "expectedRankBand": "low",
            "notes": "Instant 180 degree turnarounds are a documented synthetic simplification.",
        },
    )


def _spec_v010() -> VesselSpec:
    """V010 - coaster working a coastline-consistent track (land plausibility check).

    Steams south-southeast at 7 kn roughly parallel to the synthetic coastline, west of
    it at all times. Its in-extract window starts while it is still north of the study
    area, which is how an area-scoped AIS extract naturally behaves. Carries the
    null-island (0, 0) coordinate defect fixture.
    """
    return VesselSpec(
        vessel_id="V010", mmsi=synthetic_mmsi(10), imo=synthetic_imo(10),
        name="DEMO COASTAL WREN", type_code=70, type_label="Cargo (synthetic demonstration vessel)",
        role="Coastal-transit control", role_key="control_coastal_transit",
        role_description=(
            "Slow coastal transit whose track stays offshore and roughly parallel to the "
            "coastline - used to test land/sea plausibility rather than suspicion."
        ),
        interval_s=600, phase=2.20,
        segments=(Segment("move", 72.0, 160.0, 7.0, nav_status=0, label="coastal_transit_southbound"),),
        anchor_hour=56.0, anchor_ref=("origin_offset", 130.0, 101.0),
        expected={
            "hypothesis": "control: coastline-consistent track, no anomaly",
            "mapsToSpecCase": None,
            "inOriginRegionDuringWindow": False,
            "hasAisGap": False,
            "minDistanceToOriginKmDuringWindow": 50.0,
            "staysOffshore": True,
            "expectedRankBand": "low",
            "notes": "In-extract interval is bounded by the study-area box, not by loss of signal.",
        },
    )


def _spec_v011() -> VesselSpec:
    """V011 - harbour tug / support vessel (stops are not suspicious).

    Repeats a 12 h harbour cycle: a 6 h local box pattern at 6 kn (four 1.5 h legs,
    ~17 km per side) followed by a 6 h mooring period (0.1 kn, status 5), roughly
    115 km from the origin region and never more than ~25 km from its working corner.
    Carries the missing-optional-field defect fixtures.
    """
    cycle = (
        Segment("move", 1.5, 0.0, 6.0, nav_status=0, label="harbour_movement_north"),
        Segment("move", 1.5, 90.0, 6.0, nav_status=0, label="harbour_movement_east"),
        Segment("move", 1.5, 180.0, 6.0, nav_status=0, label="harbour_movement_south"),
        Segment("move", 1.5, 270.0, 6.0, nav_status=0, label="harbour_movement_west"),
        Segment("move", 6.0, 0.0, 0.1, nav_status=5, label="moored"),
    )
    return VesselSpec(
        vessel_id="V011", mmsi=synthetic_mmsi(11), imo=synthetic_imo(11),
        name="DEMO ANCHOR TUG", type_code=52, type_label="Tug (synthetic demonstration vessel)",
        role="Harbour tug control", role_key="control_harbour_tug",
        role_description=(
            "Local harbour movements with long mooring periods ~115 km from the origin "
            "region. Stationary periods must not be weighted as suspicious."
        ),
        interval_s=600, phase=0.95,
        segments=cycle * 6,
        anchor_hour=36.0, anchor_ref=("origin_offset", 120.0, 115.0),
        expected={
            "hypothesis": "control: legitimate stationary periods",
            "mapsToSpecCase": None,
            "inOriginRegionDuringWindow": False,
            "hasAisGap": False,
            "minDistanceToOriginKmDuringWindow": 50.0,
            "hasMooringPeriods": True,
            "expectedRankBand": "low",
            "notes": "Carries the missing-optional-field defect fixtures.",
        },
    )


def _spec_v012() -> VesselSpec:
    """V012 - distant ocean transit (proves filtering removes noise).

    Steady 13 kn north-east transit crossing the south-western corner of the study
    area, 150+ km from the origin region at all times. Carries the invalid-latitude
    defect fixture.
    """
    return VesselSpec(
        vessel_id="V012", mmsi=synthetic_mmsi(12), imo=synthetic_imo(12),
        name="DEMO FAR CURRENT", type_code=70, type_label="Cargo (synthetic demonstration vessel)",
        role="Distant transit", role_key="distractor_distant_transit",
        role_description=(
            "Distant steady transit that should be filtered out early. Included so the "
            "ranking is not distorted by irrelevant traffic."
        ),
        interval_s=600, phase=1.90,
        segments=(Segment("move", 72.0, 43.0, 13.0, nav_status=0, label="ocean_transit_northeast"),),
        anchor_hour=56.0, anchor_ref=("origin_offset", 225.0, 250.0),
        expected={
            "hypothesis": "irrelevant distant traffic",
            "mapsToSpecCase": None,
            "inOriginRegionDuringWindow": False,
            "hasAisGap": False,
            "minDistanceToOriginKmDuringWindow": 100.0,
            "expectedRankBand": "bottom",
            "notes": "Carries the invalid-latitude defect fixture.",
        },
    )


def vessel_specs() -> List[VesselSpec]:
    """All twelve synthetic vessels in stable identifier order."""
    return [
        _spec_v001(), _spec_v002(), _spec_v003(), _spec_v004(), _spec_v005(), _spec_v006(),
        _spec_v007(), _spec_v008(), _spec_v009(), _spec_v010(), _spec_v011(), _spec_v012(),
    ]


def build_context() -> Dict[str, Any]:
    """Derive the scenario geometry from the deterministic drift field.

    The observed slick is obtained by integrating the demo drift field FORWARD from the
    nominal release point, so the observation is genuinely downstream of the release
    position - the core teaching point of the demonstration.
    """
    hours_after_release = hours_between(NOMINAL_RELEASE_TIME, OBSERVATION_TIME)
    drift_path = integrate_drift(ORIGIN_CENTER[0], ORIGIN_CENTER[1], hours=hours_after_release)
    slick_lat, slick_lon = drift_path[-1][1], drift_path[-1][2]
    slick_ring = ellipse_ring(slick_lat, slick_lon, SLICK_SEMI_MAJOR_KM, SLICK_SEMI_MINOR_KM, SLICK_BEARING_DEG)
    origin_ring = ellipse_ring(
        ORIGIN_CENTER[0], ORIGIN_CENTER[1],
        ORIGIN_UNCERTAINTY_SEMI_MAJOR_KM, ORIGIN_UNCERTAINTY_SEMI_MINOR_KM,
        ORIGIN_UNCERTAINTY_BEARING_DEG,
    )
    return {
        "origin": ORIGIN_CENTER,
        "slick": (slick_lat, slick_lon),
        "originRing": origin_ring,
        "slickRing": slick_ring,
        "driftPath": [(round(h, 4), round(la, 6), round(lo, 6)) for (h, la, lo) in drift_path],
        "driftHours": hours_after_release,
        "driftDistanceKm": haversine_km(ORIGIN_CENTER[0], ORIGIN_CENTER[1], slick_lat, slick_lon),
        "driftBearingDeg": bearing_deg(ORIGIN_CENTER[0], ORIGIN_CENTER[1], slick_lat, slick_lon),
    }


# ===========================================================================
# 8. Per-vessel summaries (computed) and design self-checks
# ===========================================================================
def window_hours() -> Tuple[float, float]:
    return (
        hours_between(TRACK_START, RELEASE_WINDOW_START),
        hours_between(TRACK_START, RELEASE_WINDOW_END),
    )


def segment_timeline(spec: VesselSpec) -> List[Dict[str, Any]]:
    """Absolute segment timeline for a vessel, including gap intervals.

    These are TRACK properties (what the synthetic vessel actually did), not
    conclusions about suspicion.
    """
    out: List[Dict[str, Any]] = []
    cursor = TRACK_START
    for seg in spec.segments:
        end = cursor + timedelta(hours=seg.hours)
        out.append({
            "kind": seg.kind, "label": seg.label, "start": iso_z(cursor), "end": iso_z(end),
            "hours": seg.hours, "courseDeg": seg.course_deg, "speedKn": seg.speed_kn,
            "navStatus": seg.nav_status, "jumpKm": seg.jump_km,
        })
        cursor = end
    return out


def intentional_gaps(spec: VesselSpec) -> List[Dict[str, Any]]:
    return [
        {
            "start": s["start"], "end": s["end"], "durationHours": s["hours"],
            "label": s["label"], "intentionalJumpKm": s["jumpKm"],
            "reason": "synthetic AIS transmission gap inserted by the scenario design",
        }
        for s in segment_timeline(spec) if s["kind"] == "gap"
    ]


def gap_feasibility(spec: VesselSpec, rows: List[AisRow]) -> List[Dict[str, Any]]:
    """Bridge a vessel's intended gap(s) using the records either side.

    DATASET VALIDATION ONLY: this is arithmetic on the fixture so the generator and
    the tests can prove the scenario was built as intended. The product's AIS gap
    analysis is Phase 9 and is implemented separately, with its own rules, reasons
    and configurability.
    """
    valid = [r for r in rows if "invalid_coordinate" not in r.defects]
    out: List[Dict[str, Any]] = []
    for gap in intentional_gaps(spec):
        start_s = datetime.strptime(gap["start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
        end_s = datetime.strptime(gap["end"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
        before = [r for r in valid if r.sort_seconds < start_s]
        after = [r for r in valid if r.sort_seconds > end_s]
        entry: Dict[str, Any] = dict(gap)
        if before and after:
            last_before = max(before, key=lambda r: r.sort_seconds)
            first_after = min(after, key=lambda r: r.sort_seconds)
            dist = haversine_km(last_before.lat, last_before.lon, first_after.lat, first_after.lon)
            elapsed_h = (first_after.sort_seconds - last_before.sort_seconds) / 3600.0
            implied_kmh = dist / elapsed_h if elapsed_h > 0 else float("inf")
            entry.update({
                "lastPositionBefore": {"lat": round(last_before.lat, 6), "lon": round(last_before.lon, 6),
                                       "timestamp": last_before.timestamp},
                "firstPositionAfter": {"lat": round(first_after.lat, 6), "lon": round(first_after.lon, 6),
                                      "timestamp": first_after.timestamp},
                "bridgeDistanceKm": round(dist, 3),
                "elapsedHours": round(elapsed_h, 4),
                "impliedSpeedKmh": round(implied_kmh, 3),
                "impliedSpeedKn": round(implied_kmh / KNOT_TO_KMH, 3),
            })
        out.append(entry)
    return out


def closest_coastline_lon(lat: float) -> float:
    """Interpolate the synthetic coastline longitude at a given latitude (context only)."""
    pts = [[p[0], p[1]] for p in SYNTHETIC_COASTLINE]
    pts.sort(key=lambda p: p[1])
    if lat <= pts[0][1]:
        return pts[0][0]
    if lat >= pts[-1][1]:
        return pts[-1][0]
    for i in range(len(pts) - 1):
        lo_lat, lo_lon = pts[i][1], pts[i][0]
        hi_lat, hi_lon = pts[i + 1][1], pts[i + 1][0]
        if lo_lat <= lat <= hi_lat:
            w = 0.0 if hi_lat == lo_lat else (lat - lo_lat) / (hi_lat - lo_lat)
            return lo_lon + (hi_lon - lo_lon) * w
    return pts[-1][0]


def summarise_vessel(spec: VesselSpec, rows: List[AisRow], ctx: Dict[str, Any]) -> Dict[str, Any]:
    w0, w1 = window_hours()
    valid = [r for r in rows if "invalid_coordinate" not in r.defects]
    in_window = [r for r in valid if w0 <= r.hour <= w1]
    olat, olon = ctx["origin"]
    slat, slon = ctx["slick"]

    def min_dist(rws: Sequence[AisRow]) -> Optional[float]:
        return min(haversine_km(olat, olon, r.lat, r.lon) for r in rws) if rws else None

    def rows_inside_ring(rws: Sequence[AisRow]) -> List[AisRow]:
        return [r for r in rws if point_in_ring(r.lon, r.lat, ctx["originRing"])]

    inside_window = rows_inside_ring(in_window)
    last_row = valid[-1] if valid else None
    first_row = valid[0] if valid else None
    sog_values = [r.sog for r in valid]
    doc = [r for r in valid if r.sort_seconds >= TRACK_START.timestamp()]
    gaps = gap_feasibility(spec, rows)
    anchor_lat, anchor_lon = resolve_anchor(spec.anchor_ref, ctx)

    summary: Dict[str, Any] = {
        "vesselId": spec.vessel_id,
        "mmsi": spec.mmsi,
        "imo": spec.imo,
        "name": spec.name,
        "typeCode": spec.type_code,
        "typeLabel": spec.type_label,
        "role": spec.role,
        "roleKey": spec.role_key,
        "roleDescription": spec.role_description,
        "reportingIntervalSeconds": spec.interval_s,
        "recordCount": len(rows),
        "validRecordCount": len(valid),
        "firstRecordTimestamp": first_row.timestamp if first_row else None,
        "lastRecordTimestamp": last_row.timestamp if last_row else None,
        "inStudyAreaHours": round((last_row.hour - first_row.hour), 4) if (first_row and last_row) else 0.0,
        "recordsInReleaseWindow": len(in_window),
        "recordsInsideOriginRegionDuringWindow": len(inside_window),
        "insideOriginRegionDuringWindow": bool(inside_window),
        "minDistanceToOriginKmDuringWindow": round(min_dist(in_window), 3) if min_dist(in_window) is not None else None,
        "minDistanceToOriginKmWholeTrack": round(min_dist(valid), 3) if valid else None,
        "hourOfClosestApproachToOrigin": (
            round(min(valid, key=lambda r: haversine_km(olat, olon, r.lat, r.lon)).hour, 4) if valid else None
        ),
        "distanceToSlickKmAtObservation": (
            round(haversine_km(slat, slon, last_row.lat, last_row.lon), 3) if last_row else None
        ),
        "minSogKn": round(min(sog_values), 3) if sog_values else None,
        "maxSogKn": round(max(sog_values), 3) if sog_values else None,
        "meanSogKn": round(sum(sog_values) / len(sog_values), 3) if sog_values else None,
        "sogSpreadKn": round(max(sog_values) - min(sog_values), 3) if sog_values else None,
        "stationaryRecords": sum(1 for r in valid if r.sog < 1.0),
        "anchorPosition": {"lat": round(anchor_lat, 6), "lon": round(anchor_lon, 6)},
        "anchorHour": spec.anchor_hour,
        "intentionalGaps": gaps,
        "segmentTimeline": segment_timeline(spec),
        "injectedDefects": sorted({d for r in rows for d in r.defects}),
        "expected": spec.expected,
    }
    if spec.vessel_id == "V010":
        offshore = [r for r in valid if r.lon < closest_coastline_lon(r.lat)]
        summary["recordsOffshoreOfSyntheticCoastline"] = len(offshore)
        summary["allRecordsOffshore"] = len(offshore) == len(valid)
    if spec.vessel_id == "V011":
        summary["maxDistanceFromAnchorKm"] = round(
            max(haversine_km(anchor_lat, anchor_lon, r.lat, r.lon) for r in valid), 3
        ) if valid else None
    return summary


def self_check(
    specs: List[VesselSpec], rows: List[AisRow], defects: List[Dict[str, Any]],
    summaries: List[Dict[str, Any]], ctx: Dict[str, Any],
) -> List[str]:
    """Verify that the generated scenario has the properties it claims to have.

    This validates the DATASET DESIGN, not any forensic conclusion. Failing here means
    the synthetic scenario itself is wrong, so the generator refuses to write output.
    """
    checks: List[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            raise RuntimeError(f"dataset design self-check FAILED: {message}")
        checks.append(message)

    by_id = {s["vesselId"]: s for s in summaries}
    w0, w1 = window_hours()

    check(len(specs) == 12, "exactly 12 vessel specifications")
    check(len({s.mmsi for s in specs}) == 12, "12 unique MMSI values")
    check(len({s.imo for s in specs}) == 12, "12 unique IMO values")
    check(len({s.name for s in specs}) == 12, "12 unique vessel names")
    check(all(by_id[s.vessel_id]["recordCount"] > 0 for s in specs),
          "every vessel has at least one record inside the study area")

    check(by_id["V001"]["insideOriginRegionDuringWindow"],
          "V001 is inside the probable-origin region during the release window")
    check(by_id["V001"]["minSogKn"] is not None and by_id["V001"]["minSogKn"] <= 3.0,
          "V001 shows a pronounced slowdown (min SOG <= 3 kn)")

    v002_gap = by_id["V002"]["intentionalGaps"][0]
    check(by_id["V002"]["insideOriginRegionDuringWindow"],
          "V002 is inside the probable-origin region during the release window")
    check(abs(v002_gap["durationHours"] - 4.0) < 1e-9, "V002 has a 4 hour AIS transmission gap")
    check(v002_gap["impliedSpeedKn"] <= 15.0,
          f"V002's gap is physically feasible ({v002_gap['impliedSpeedKn']:.1f} kn <= 15 kn)")

    v003_gap = by_id["V003"]["intentionalGaps"][0]
    check(abs(v003_gap["durationHours"] - 4.0) < 1e-9, "V003 has a 4 hour AIS transmission gap")
    check(v003_gap["impliedSpeedKn"] >= 30.0,
          f"V003's gap is NOT physically feasible ({v003_gap['impliedSpeedKn']:.1f} kn >= 30 kn)")

    check(by_id["V004"]["distanceToSlickKmAtObservation"] is not None
          and by_id["V004"]["distanceToSlickKmAtObservation"] <= 15.0,
          "V004 is the vessel nearest the observed slick at observation time")
    check(min(by_id[s.vessel_id]["distanceToSlickKmAtObservation"] for s in specs
              if by_id[s.vessel_id]["distanceToSlickKmAtObservation"] is not None
              ) == by_id["V004"]["distanceToSlickKmAtObservation"],
          "no other vessel is closer to the observed slick at observation time")
    check(by_id["V004"]["minDistanceToOriginKmDuringWindow"] >= 100.0,
          f"V004 stays >= 100 km from the origin during the window "
          f"({by_id['V004']['minDistanceToOriginKmDuringWindow']:.1f} km)")

    check(by_id["V005"]["minDistanceToOriginKmDuringWindow"] >= 100.0,
          f"V005 is spatially incompatible during the window "
          f"({by_id['V005']['minDistanceToOriginKmDuringWindow']:.1f} km)")
    check(by_id["V005"]["minDistanceToOriginKmWholeTrack"] <= 5.0,
          "V005 does cross the origin region, but only after the window closes")
    check(by_id["V005"]["hourOfClosestApproachToOrigin"] > w1,
          "V005's closest approach happens after the release window ends")

    check(by_id["V006"]["minDistanceToOriginKmDuringWindow"] >= 150.0,
          f"V006 (behavioural anomaly) stays >= 150 km from the origin "
          f"({by_id['V006']['minDistanceToOriginKmDuringWindow']:.1f} km)")
    check(by_id["V006"]["sogSpreadKn"] >= 4.0,
          f"V006 shows strong speed variability ({by_id['V006']['sogSpreadKn']:.1f} kn spread)")

    check(by_id["V007"]["sogSpreadKn"] <= 0.5,
          "V007 (control) holds a steady speed")
    check(by_id["V007"]["minDistanceToOriginKmDuringWindow"] >= 50.0,
          "V007 (control) is not spatially compatible")
    check(by_id["V008"]["stationaryRecords"] >= 20 and by_id["V008"]["minDistanceToOriginKmDuringWindow"] >= 100.0,
          "V008 has many stationary periods yet is far from the origin")
    check(by_id["V009"]["maxSogKn"] >= 18.0 and by_id["V009"]["minDistanceToOriginKmDuringWindow"] >= 50.0,
          "V009 is fast and steady yet not spatially compatible")
    check(by_id["V010"]["allRecordsOffshore"] is True,
          "V010's valid records all lie west of the synthetic coastline")
    check(by_id["V011"]["stationaryRecords"] >= 20 and by_id["V011"]["maxDistanceFromAnchorKm"] <= 30.0,
          "V011 works locally with long moored periods")
    check(by_id["V012"]["minDistanceToOriginKmDuringWindow"] >= 100.0,
          "V012 stays far from the origin region")

    slick_distance = ctx["driftDistanceKm"]
    check(slick_distance >= 20.0,
          f"the observed slick is {slick_distance:.1f} km from the release point (observed != released)")
    check(not point_in_ring(ctx["slick"][1], ctx["slick"][0], ctx["originRing"]),
          "the observed slick centroid lies OUTSIDE the origin uncertainty region")
    check(point_in_ring(ORIGIN_CENTER[1], ORIGIN_CENTER[0], ctx["originRing"]),
          "the origin uncertainty region contains the scenario release point")
    check(RELEASE_WINDOW_END <= OBSERVATION_TIME and RELEASE_WINDOW_START < RELEASE_WINDOW_END,
          "the release window lies entirely before the observation time")
    check(ring_area_km2(ctx["slickRing"]) >= 20.0,
          f"slick area is {ring_area_km2(ctx['slickRing']):.1f} km2")

    categories: Dict[str, int] = {}
    for d in defects:
        categories[d["category"]] = categories.get(d["category"], 0) + 1
    expected_categories = {
        "duplicate_record": 4, "malformed_timestamp": 2, "invalid_coordinate": 2,
        "negative_speed": 1, "impossible_speed_jump": 1, "missing_optional_field": 3,
    }
    for category, count in expected_categories.items():
        check(categories.get(category, 0) == count,
              f"{count} injected '{category}' defect(s) present")

    check(all(r.vessel_type > 0 for r in rows), "all records carry an AIS ship-type code")
    check(all(r.mmsi == r.mmsi.strip() for r in rows), "MMSI values are clean strings")
    return checks


# ===========================================================================
# 9. Assembly, JSON builders, CSV writer and manifest
# ===========================================================================
def assemble(specs: List[VesselSpec], ctx: Dict[str, Any]):
    """Build every vessel's rows, inject the defect fixtures and summarise."""
    rows_by_vessel = {spec.vessel_id: build_vessel_rows(spec, ctx) for spec in specs}
    defects = inject_defects(rows_by_vessel)
    rows: List[AisRow] = []
    for spec in specs:
        rows.extend(rows_by_vessel[spec.vessel_id])
    rows.sort(key=lambda r: (r.sort_seconds, r.mmsi, r.seq))
    summaries = [summarise_vessel(spec, rows_by_vessel[spec.vessel_id], ctx) for spec in specs]
    return rows_by_vessel, rows, defects, summaries


def observation_footprint() -> Dict[str, Any]:
    margin = 0.5
    min_lat = STUDY_BBOX["minLat"] - margin
    max_lat = STUDY_BBOX["maxLat"] + margin
    min_lon = STUDY_BBOX["minLon"] - margin
    max_lon = STUDY_BBOX["maxLon"] + margin
    ring = [
        [round(min_lon, 6), round(min_lat, 6)],
        [round(max_lon, 6), round(min_lat, 6)],
        [round(max_lon, 6), round(max_lat, 6)],
        [round(min_lon, 6), round(max_lat, 6)],
        [round(min_lon, 6), round(min_lat, 6)],
    ]
    return {
        "type": "Polygon",
        "coordinates": [ring],
        "bounds": {"minLat": round(min_lat, 6), "maxLat": round(max_lat, 6),
                   "minLon": round(min_lon, 6), "maxLon": round(max_lon, 6)},
    }


def build_slick_json(ctx: Dict[str, Any]) -> Dict[str, Any]:
    ring = ctx["slickRing"]
    return {
        "synthetic": True,
        "datasetLabel": DATASET_LABEL,
        "uiLabel": "DEMO DATA",
        "caseId": CASE_ID,
        "spillId": SPILL_ID,
        "acquisitionTime": iso_z(OBSERVATION_TIME),
        "sensor": {
            "name": "synthetic demonstration SAR scene",
            "band": "C-band SAR-like (demonstration stand-in, not a real acquisition)",
            "synthetic": True,
        },
        "detectionConfidence": DETECTION_CONFIDENCE,
        "detectionConfidenceNote": (
            "Prototype confidence for the synthetic scene. It is NOT a scientifically "
            "validated detection probability and does not constitute ground truth."
        ),
        "lookAlikeWarning": False,
        "lookAlikeAssessment": {
            "checkedClasses": ["low wind area", "natural or biogenic film", "radar artefact", "sea-state variation"],
            "lowWindArea": False,
            "lowWindNote": (
                f"A moderate {WIND_SPEED_MS:.0f} m/s wind is prescribed by the synthetic scenario, "
                "which argues against a low-wind look-alike."
            ),
            "otherClasses": "not indicated by the synthetic scenario; a real investigation still needs confirmation",
        },
        "areaKm2": round(ring_area_km2(ring), 3),
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "centroid": {"lat": round(ctx["slick"][0], 6), "lon": round(ctx["slick"][1], 6)},
        "boundingBox": ring_bounds(ring),
        "perimeterKm": round(ring_perimeter_km(ring), 3),
        "approximateLengthKm": round(2.0 * SLICK_SEMI_MAJOR_KM, 3),
        "approximateWidthKm": round(2.0 * SLICK_SEMI_MINOR_KM, 3),
        "orientationDeg": SLICK_BEARING_DEG,
        "orientationNote": "Major axis of the elliptical synthetic slick, degrees clockwise from north.",
        "provenance": "model-derived scenario asset (pre-computed for demo mode: no imagery processing at run time)",
    }


def build_origin_expected_json(specs, summaries, ctx) -> Dict[str, Any]:
    """Ground truth of the synthetic scenario.

    TEST FIXTURE ONLY. This file must never be rendered as an investigation conclusion:
    a real investigation receives the model's uncertainty region and confidence, not the
    scenario author's answer key.
    """
    by_id = {s["vesselId"]: s for s in summaries}
    return {
        "synthetic": True,
        "datasetLabel": DATASET_LABEL,
        "fixturePurpose": "Phase 19 test fixture and generator self-check input ONLY",
        "warning": (
            "This file contains the scenario answer key. It must never be shown to an "
            "investigator as a result and must never be used by the analysis pipeline "
            "as an input. The product reports a probable origin region with uncertainty."
        ),
        "caseId": CASE_ID,
        "trueReleasePoint": {"lat": round(ORIGIN_CENTER[0], 6), "lon": round(ORIGIN_CENTER[1], 6)},
        "nominalReleaseTime": iso_z(NOMINAL_RELEASE_TIME),
        "releaseWindow": {"start": iso_z(RELEASE_WINDOW_START), "end": iso_z(RELEASE_WINDOW_END)},
        "expectedOriginRegion": {
            "type": "Polygon",
            "coordinates": [ctx["originRing"]],
            "centroid": {"lat": round(ORIGIN_CENTER[0], 6), "lon": round(ORIGIN_CENTER[1], 6)},
            "uncertaintyRadiusKm": ORIGIN_UNCERTAINTY_SEMI_MAJOR_KM,
            "semiMajorKm": ORIGIN_UNCERTAINTY_SEMI_MAJOR_KM,
            "semiMinorKm": ORIGIN_UNCERTAINTY_SEMI_MINOR_KM,
            "orientationDeg": ORIGIN_UNCERTAINTY_BEARING_DEG,
            "areaKm2": round(ring_area_km2(ctx["originRing"]), 3),
            "note": "The ellipse is the scenario's uncertainty region, not a point estimate.",
        },
        "driftModelUsed": {
            "description": "forward integration of the demo drift field from the release point to the observation",
            "windageCoefficient": WINDAGE_COEFFICIENT,
            "integrationStepSeconds": DRIFT_STEP_SECONDS,
            "driftHours": round(ctx["driftHours"], 4),
            "driftDistanceKm": round(ctx["driftDistanceKm"], 3),
            "driftBearingDeg": round(ctx["driftBearingDeg"], 3),
            "computedSlickCentroid": {"lat": round(ctx["slick"][0], 6), "lon": round(ctx["slick"][1], 6)},
            "driftPath": [[round(lo, 6), round(la, 6)] for (_h, la, lo) in ctx["driftPath"]],
            "parametersArePrototypeValues": True,
        },
        "expectedGapFixtures": [
            {"vesselId": s["vesselId"], **gap}
            for s in summaries for gap in s["intentionalGaps"]
        ],
        "expectedAnomalyFixtures": [
            {
                "vesselId": "V001", "type": "slowdown_and_loitering",
                "timing": "slow segment covers the release window inside the origin region",
                "minSogKnObserved": by_id["V001"]["minSogKn"],
                "baselineSogKn": 11.5,
            },
            {
                "vesselId": "V004", "type": "slow_loiter_near_observed_slick_after_release_window",
                "minSogKnObserved": by_id["V004"]["minSogKn"],
                "distanceToSlickKmAtObservation": by_id["V004"]["distanceToSlickKmAtObservation"],
            },
            {
                "vesselId": "V006", "type": "erratic_speed_and_course_changes",
                "sogSpreadKnObserved": by_id["V006"]["sogSpreadKn"],
                "minDistanceToOriginKmDuringWindow": by_id["V006"]["minDistanceToOriginKmDuringWindow"],
            },
            {
                "vesselId": "V008", "type": "legitimate_stationary_working_periods",
                "stationaryRecords": by_id["V008"]["stationaryRecords"],
                "note": "included so that a slow vessel far from the origin is NOT promoted",
            },
        ],
        "expectedDistances": [
            {
                "vesselId": s["vesselId"],
                "minDistanceToOriginKmDuringWindow": s["minDistanceToOriginKmDuringWindow"],
                "distanceToSlickKmAtObservation": s["distanceToSlickKmAtObservation"],
                "hourOfClosestApproachToOrigin": s["hourOfClosestApproachToOrigin"],
                "insideOriginRegionDuringWindow": s["insideOriginRegionDuringWindow"],
            }
            for s in summaries
        ],
        "observedVsRelease": {
            "observedSlickCentroid": {"lat": round(ctx["slick"][0], 6), "lon": round(ctx["slick"][1], 6)},
            "releasePoint": {"lat": round(ORIGIN_CENTER[0], 6), "lon": round(ORIGIN_CENTER[1], 6)},
            "separationKm": round(ctx["driftDistanceKm"], 3),
            "teachingPoint": (
                "The observed slick is tens of kilometres downstream of the release point, so "
                "proximity to the slick is not proximity to the release location."
            ),
        },
        "vesselSummaries": summaries,
    }


def build_expected_ranking_json() -> Dict[str, Any]:
    """Intended ordering PROPERTIES of the scenario (targets for Phase 10 and Phase 19).

    Deliberately expressed as inequalities rather than one exact ordering: the scoring
    engine does not exist yet, and the dataset must not pretend to know its exact output.
    """
    return {
        "synthetic": True,
        "datasetLabel": DATASET_LABEL,
        "caseId": CASE_ID,
        "status": "intended properties of the synthetic scenario, to be satisfied by the Phase 10 scoring engine",
        "expectedOrderingProperties": [
            {"property": "V001 and V002 form the top two candidates", "reason": "both are inside the origin region during the release window with compatible movement"},
            {"property": "V003 ranks strictly below V002", "reason": "same location and gap timing, but V003's gap is physically impossible"},
            {"property": "V004 is not ranked first", "reason": "nearest to the observed slick but 100+ km from the origin during the window"},
            {"property": "V005 ranks below V001 and V002", "reason": "crosses the origin region only after the release window closes"},
            {"property": "V006 is not in the top five", "reason": "strong behavioural anomaly but 150+ km from the origin region"},
            {"property": "every control/distractor vessel ranks below at least one of V001 or V002", "reason": "no distractor should outrank a compatible candidate"},
            {"property": "V007 (no gap, steady, 90 km away) is not promoted by its missing gap", "reason": "absence of a gap must not be treated as evidence"},
            {"property": "V004 outranks V006 in any proximity-based comparison involving the slick", "reason": "proximity to the slick is not proximity to the release location"},
        ],
        "topCandidates": ["V001", "V002"],
        "mustNotRankFirst": ["V004"],
        "mustRankBelow": {
            "V003": ["V002"],
            "V004": ["V001", "V002"],
            "V005": ["V001", "V002"],
            "V006": ["V001", "V002", "V003"],
            "V007": ["V001", "V002"],
            "V008": ["V001", "V002"],
            "V009": ["V001", "V002"],
            "V010": ["V001", "V002"],
            "V011": ["V001", "V002"],
            "V012": ["V001", "V002"],
        },
        "expectedRankBands": {
            "V001": "top-2", "V002": "top-2", "V003": "top-3 but below V002",
            "V004": "mid (never first)", "V005": "below V001 and V002", "V006": "outside top-5",
            "V007": "mid", "V008": "low", "V009": "low", "V010": "low", "V011": "low", "V012": "bottom",
        },
        "testCaseMapping": {
            "A_correct_location_and_time": "V001",
            "B_correct_location_wrong_time": "V005",
            "C_wrong_location_correct_time": "V006 (and V004 for the slick-proximity trap)",
            "D_gap_with_impossible_travel": "V003",
            "E_gap_physically_compatible": "V002",
            "F_anomaly_without_location": "V006",
            "G_nearest_vessel_not_highest_scoring": "V004 vs V001/V002",
        },
        "disclaimer": DISCLAIMER,
    }


def build_case_json(specs, rows, defects, summaries, ctx) -> Dict[str, Any]:
    """The investigation configuration: INPUTS only, no answer key."""
    intervals = [s.interval_s for s in specs]
    return {
        "caseId": CASE_ID,
        "title": "Synthetic oil-spill attribution demonstration case",
        "dataMode": "demo",
        "synthetic": True,
        "datasetLabel": DATASET_LABEL,
        "disclaimer": DISCLAIMER,
        "generatedBy": {
            "script": "intelligence/data/demo/generate_case_001.py",
            "version": GENERATOR_VERSION,
            "deterministic": True,
            "randomnessUsed": False,
        },
        "studyArea": {
            "label": (
                "Synthetic offshore study area (approximate geography used as a container for "
                "the demonstration; no real incident is referenced or implied)"
            ),
            "boundingBox": STUDY_BBOX,
            "centerPoint": {
                "lat": round((STUDY_BBOX["minLat"] + STUDY_BBOX["maxLat"]) / 2.0, 6),
                "lon": round((STUDY_BBOX["minLon"] + STUDY_BBOX["maxLon"]) / 2.0, 6),
            },
            "syntheticCoastline": SYNTHETIC_COASTLINE,
            "coastlineNote": (
                "Coarse synthetic polyline used only for land/sea plausibility context. It is "
                "not survey data and must not be used for navigation."
            ),
        },
        "aisExtract": {
            "mode": "area-scoped extract",
            "boundingBox": STUDY_BBOX,
            "windowStart": iso_z(TRACK_START),
            "windowEnd": iso_z(OBSERVATION_TIME),
            "windowHours": TRACK_HOURS,
            "vesselCount": len(specs),
            "mmsiList": [s.mmsi for s in specs],
            "reportingIntervalSecondsRange": [min(intervals), max(intervals)],
            "file": "ais/demo_ais_positions.csv",
            "recordCount": len(rows),
            "label": "AIS: Synthetic Demonstration Dataset",
            "notes": [
                "Positions outside the bounding box are intentionally absent, so some vessels "
                "begin or end mid-track; that is ordinary behaviour for an area-scoped extract",
                "Records are ordered by timestamp; malformed-timestamp fixture rows keep their "
                "intended position in that ordering",
                "Every row carries datasetLabel='Synthetic Demonstration Dataset'",
                "No cleaning, filtering or scoring has been applied to these records",
            ],
        },
        "observation": {
            "observedAt": iso_z(OBSERVATION_TIME),
            "sensor": {
                "name": "synthetic demonstration SAR scene",
                "band": "C-band SAR-like (demonstration stand-in, not a real acquisition)",
                "synthetic": True,
            },
            "sceneDescription": (
                "Bundled demonstration scene: detection is modelled on the pre-computed slick "
                "polygon delivered with the case, so the demo runs with no imagery download."
            ),
            "footprint": observation_footprint(),
            "environmentalConditionsSummary": {
                "windSpeedMs": WIND_SPEED_MS,
                "windFromDirectionDeg": WIND_FROM_DEG,
                "surfaceCurrentBaseMs": [CURRENT_BASE_U, CURRENT_BASE_V],
                "note": "synthetic, steady field (see environmental/demo_environmental_field.json)",
            },
            "slickFile": "demo_slick.json",
            "detectionConfidence": DETECTION_CONFIDENCE,
            "lookAlikeWarning": False,
        },
        "origin": {
            "releaseWindow": {"start": iso_z(RELEASE_WINDOW_START), "end": iso_z(RELEASE_WINDOW_END)},
            "uncertaintyRadiusKm": ORIGIN_UNCERTAINTY_SEMI_MAJOR_KM,
            "uncertaintyShape": "ellipse (prototype representation of an uncertainty region)",
            "notes": [
                "The release window and origin region are INPUTS of this case used to build the "
                "scenario; the product must reconstruct them from the slick and environmental "
                "data, and must report them as estimates with uncertainty",
                "No single-point origin is published anywhere in the case configuration",
            ],
        },
        "reservedOriginFixtureFile": "demo_origin_expected.json",
        "reservedOriginFixtureNote": (
            "Answer key for automated tests only. It is NOT an input to the analysis pipeline "
            "and must never be surfaced by the API, the dashboard or a report."
        ),
        "environment": {
            "file": "environmental/demo_environmental_field.json",
            "provider": "DemoEnvironmentalProvider",
            "deterministic": True,
            "windageCoefficient": WINDAGE_COEFFICIENT,
        },
        "vessels": [
            {
                "vesselId": s.vessel_id,
                "mmsi": s.mmsi,
                "imo": s.imo,
                "name": s.name,
                "typeCode": s.type_code,
                "typeLabel": s.type_label,
                "role": s.role,
                "roleKey": s.role_key,
                "roleDescription": s.role_description,
                "reportingIntervalSeconds": s.interval_s,
                "synthetic": True,
                "syntheticIdentityNote": (
                    "Synthetic identity for the demonstration dataset. It is not asserted to "
                    "correspond to any real vessel or voyage."
                ),
            }
            for s in specs
        ],
        "expectedOutcome": {
            "file": "expected_ranking.json",
            "summary": "intended ordering properties of the scenario (targets for Phase 10)",
        },
        "injectedDefects": defects,
        "counts": {
            "vessels": len(specs),
            "records": len(rows),
            "vesselsWithIntentionalGap": sorted({s["vesselId"] for s in summaries if s["intentionalGaps"]}),
            "defectRows": sum(1 for r in rows if r.defects),
            "defectsByCategory": _count_by(defects, "category"),
        },
    }


def _count_by(items: Sequence[Dict[str, Any]], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for item in items:
        out[item[key]] = out.get(item[key], 0) + 1
    return dict(sorted(out.items()))


def write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(round_floats(payload), fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def write_ais_csv(path: str, rows: Sequence[AisRow]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            writer.writerow(row.to_csv())


#: Files that make up the dataset, in a fixed order (used for hashing).
DATASET_FILES = (
    "case_001.json",
    "demo_slick.json",
    "demo_origin_expected.json",
    "expected_ranking.json",
    "environmental/demo_environmental_field.json",
    "ais/demo_ais_positions.csv",
)
MANIFEST_FILE = "manifest.json"


def build_manifest(out_dir: str, rows: Sequence[AisRow], defects: Sequence[Dict[str, Any]],
                   summaries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    entries = []
    for rel in DATASET_FILES:
        path = os.path.join(out_dir, rel)
        with open(path, "rb") as fh:
            payload = fh.read()
        entries.append({
            "path": rel,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    return {
        "synthetic": True,
        "datasetLabel": DATASET_LABEL,
        "caseId": CASE_ID,
        "generatorVersion": GENERATOR_VERSION,
        "generatorScript": "intelligence/data/demo/generate_case_001.py",
        "randomnessUsed": False,
        "reproducible": (
            "Re-running the generator with the same source reproduces these hashes byte for "
            "byte; intelligence/tests/test_case_001_dataset.py asserts this."
        ),
        "timezone": "all timestamps are UTC (ISO-8601 with trailing Z)",
        "files": entries,
        "counts": {
            "vessels": len(summaries),
            "aisRecords": len(rows),
            "defectRows": sum(1 for r in rows if r.defects),
            "defectsByCategory": _count_by(defects, "category"),
        },
    }


def write_dataset(out_dir: str, specs, rows, defects, summaries, ctx) -> List[str]:
    os.makedirs(os.path.join(out_dir, "ais"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "environmental"), exist_ok=True)
    write_json(os.path.join(out_dir, "case_001.json"), build_case_json(specs, rows, defects, summaries, ctx))
    write_json(os.path.join(out_dir, "demo_slick.json"), build_slick_json(ctx))
    write_json(os.path.join(out_dir, "demo_origin_expected.json"), build_origin_expected_json(specs, summaries, ctx))
    write_json(os.path.join(out_dir, "expected_ranking.json"), build_expected_ranking_json())
    write_json(os.path.join(out_dir, "environmental", "demo_environmental_field.json"), environmental_field())
    write_ais_csv(os.path.join(out_dir, "ais", "demo_ais_positions.csv"), rows)
    manifest = build_manifest(out_dir, rows, defects, summaries)
    write_json(os.path.join(out_dir, MANIFEST_FILE), manifest)
    return list(DATASET_FILES) + [MANIFEST_FILE]


# ===========================================================================
# 10. Command line entry point
# ===========================================================================
def _num(value: Any, width: int = 9, decimals: int = 1) -> str:
    if value is None:
        return "-".rjust(width)
    return f"{value:.{decimals}f}".rjust(width)


def print_summary(specs, rows, defects, summaries, ctx, checks, written, out_dir) -> None:
    line = "=" * 118
    print(line)
    print("ABYSS - CASE-001 synthetic demonstration dataset")
    print(f"  label: {DATASET_LABEL}   |   mode: demo   |   randomness: none (fully deterministic)")
    print(line)
    print("SCENARIO GEOMETRY (synthetic)")
    print(f"  AIS extract window      : {iso_z(TRACK_START)}  ->  {iso_z(OBSERVATION_TIME)}  ({TRACK_HOURS:.0f} h)")
    print(f"  observation time        : {iso_z(OBSERVATION_TIME)}")
    print(f"  release window          : {iso_z(RELEASE_WINDOW_START)}  ->  {iso_z(RELEASE_WINDOW_END)}")
    print(f"  release point (fixture) : {ORIGIN_CENTER[0]:.4f} N, {ORIGIN_CENTER[1]:.4f} E")
    print(f"  observed slick centroid : {ctx['slick'][0]:.4f} N, {ctx['slick'][1]:.4f} E")
    print(f"  observed != released by : {ctx['driftDistanceKm']:.1f} km on bearing {ctx['driftBearingDeg']:.1f} deg")
    print(f"  drift field             : {WIND_SPEED_MS:.0f} m/s wind from {WIND_FROM_DEG:.0f} deg, "
          f"current {CURRENT_BASE_U:.2f}/{CURRENT_BASE_V:.2f} m/s, windage {WINDAGE_COEFFICIENT}")
    print()
    header = (f"  {'ID':<5}{'ROLE KEY':<34}{'RECS':>6}{'IN-WIN':>7}"
              f"{'MIN->ORIGIN':>12}{'->SLICK':>9}{'MIN SOG':>9}{'MAX SOG':>9}{'STOPS':>7}{'GAPS':>6}{'DEFECTS':>8}")
    print(header)
    print("  " + "-" * 116)
    for s in summaries:
        print(f"  {s['vesselId']:<5}{s['roleKey']:<34}{s['recordCount']:>6}{s['recordsInReleaseWindow']:>7}"
              f"{_num(s['minDistanceToOriginKmDuringWindow'], 12)}{_num(s['distanceToSlickKmAtObservation'], 9)}"
              f"{_num(s['minSogKn'], 9)}{_num(s['maxSogKn'], 9)}"
              f"{s['stationaryRecords']:>7}{len(s['intentionalGaps']):>6}{len(s['injectedDefects']):>8}")
    print("  " + "-" * 116)
    print(f"  MIN->ORIGIN = minimum distance (km) to the probable-origin centre while inside the "
          f"release window; ->SLICK = distance (km) to the observed slick at observation time")
    print()
    print("INTENTIONAL AIS TRANSMISSION GAPS")
    for s in summaries:
        for gap in s["intentionalGaps"]:
            feasible = "FEASIBLE" if gap.get("impliedSpeedKn", 0) <= 15.0 else "NOT FEASIBLE"
            print(f"  {s['vesselId']}  {gap['start']} -> {gap['end']}  ({gap['durationHours']:.0f} h)  "
                  f"bridge {gap.get('bridgeDistanceKm', 0):.1f} km  implied {gap.get('impliedSpeedKn', 0):.1f} kn  {feasible}")
            print(f"        role: {s['role']}")
    print()
    print("INJECTED DATA-QUALITY DEFECTS (Phase 3 cleaning targets)")
    for category, count in sorted(_count_by(defects, "category").items()):
        vessels = sorted({d["vesselId"] for d in defects if d["category"] == category})
        print(f"  {category:<24} {count:>3} row(s)  vessels: {', '.join(vessels)}")
    print()
    print("TOTALS")
    print(f"  vessels: {len(specs)}   AIS records: {len(rows)}   rows carrying a defect: "
          f"{sum(1 for r in rows if r.defects)}")
    print(f"  generator self-checks passed: {len(checks)}")
    print()
    print(f"FILES WRITTEN ({out_dir})")
    for rel in written:
        size = os.path.getsize(os.path.join(out_dir, rel))
        print(f"  {rel:<46} {size:>9} bytes")
    print(line)
    print("DISCLAIMER: this dataset is synthetic and exists to test the forensic pipeline.")
    print("Nothing here asserts that any vessel caused an oil spill; ABYSS produces candidate")
    print("vessels whose recorded movement is compatible with a reconstructed origin and window.")
    print(line)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic ABYSS CASE-001 synthetic demonstration dataset.",
    )
    parser.add_argument(
        "--out-dir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "case_001"),
        help="directory to write the dataset into (default: ./case_001 next to this script)",
    )
    parser.add_argument("--quiet", action="store_true", help="do not print the summary table")
    args = parser.parse_args(argv)

    ctx = build_context()
    specs = vessel_specs()
    _rows_by_vessel, rows, defects, summaries = assemble(specs, ctx)
    checks = self_check(specs, rows, defects, summaries, ctx)
    written = write_dataset(args.out_dir, specs, rows, defects, summaries, ctx)

    if not args.quiet:
        print_summary(specs, rows, defects, summaries, ctx, checks, written, args.out_dir)
    else:
        print(f"wrote {len(written)} files to {args.out_dir} ({len(rows)} AIS records, "
              f"{len(checks)} self-checks passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
