"""ABYSS - origin-region estimation by backward drift (Phase 11).

PURPOSE
    Reconstruct WHERE the observed oil could have been released and report it
    as a REGION with confidence - never a single point. The observed slick at
    the observation time is treated as a cloud of particles; each particle is
    integrated BACKWARD through the environmental field across the candidate
    release window; the convex hull of all particle positions at times inside
    the window becomes the estimated origin region (GeoJSON Polygon).

WHY A REGION, NOT A POINT
    docs/methodology.md and the case input both forbid publishing a single-point
    origin: uncertainty in windage, current sampling and window timing grows
    with drift time, so honesty demands an area with a confidence value.

WHY THE CANDIDATE WINDOW IS AN INPUT
    A steady demo field carries no clock - drift alone cannot say how long the
    oil has travelled. The candidate release window (a prior supplied with the
    case, exactly what an investigator would bound the search by) limits the
    hindcast integration. What THIS module reconstructs from slick +
    environmental data is the region, its spread and its confidence; the window
    is carried through with provenance and always reported as an estimate.

MODEL
    Backward forward-Euler integration of drift = current + windage*wind with a
    fixed step (default 300 s - the scenario generator's own step, so the
    inverse run retraces the forward path at demo accuracy). A PROTOTYPE
    scheme: not a validated ocean model (docs/methodology.md).

CONFIDENCE
    Derived from the spatial spread of the particle cloud against a documented
    reference radius: a tight cloud gives a tight region and higher confidence.
    It measures internal consistency of THIS model with THIS field - not
    scientific accuracy, and never a probability of guilt.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

if __package__ in (None, ""):  # executed directly as a script
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.geo import convex_hull, distance_to_ring_km, point_in_ring, polygon_area_km2
    from app.hindcast.environmental import EnvironmentalField
    from app.timeutils import ReleaseWindow, parse_iso_z
else:
    from app.geo import convex_hull, distance_to_ring_km, point_in_ring, polygon_area_km2
    from app.hindcast.environmental import EnvironmentalField
    from app.timeutils import ReleaseWindow, parse_iso_z

__all__ = ["OriginHindcastError", "OriginConfig", "OriginEstimate", "estimate_origin"]


class OriginHindcastError(RuntimeError):
    """Raised when the hindcast cannot produce a usable region."""


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class OriginConfig:
    """Tunable hindcast parameters. Defaults suit the demo bundle.

    Every value is a PROTOTYPE choice reported in the output - none is a
    calibrated constant (docs/methodology.md).
    """

    step_seconds: float = 300.0            # integration step (matches generator)
    sample_hours: float = 0.5              # particle snapshot cadence
    windage: Optional[float] = None        # None -> the field's own coefficient
    region_buffer_km: float = 2.0          # positional safety margin around the hull
    boundary_stride: int = 2               # use every Nth slick boundary vertex as a seed
    confidence_spread_reference_km: float = 30.0

    def __post_init__(self) -> None:
        if self.step_seconds <= 0:
            raise ValueError(f"step_seconds must be > 0, got {self.step_seconds}")
        if self.sample_hours <= 0:
            raise ValueError(f"sample_hours must be > 0, got {self.sample_hours}")
        if self.sample_hours * 3600.0 < self.step_seconds:
            raise ValueError("sample_hours must cover at least one integration step")
        if self.boundary_stride < 1:
            raise ValueError(f"boundary_stride must be >= 1, got {self.boundary_stride}")
        if self.region_buffer_km < 0:
            raise ValueError(f"region_buffer_km must be >= 0, got {self.region_buffer_km}")
        if self.confidence_spread_reference_km <= 0:
            raise ValueError("confidence_spread_reference_km must be > 0")
        if self.windage is not None and not (0.0 <= self.windage <= 1.0):
            raise ValueError(f"windage must be in [0, 1] or None, got {self.windage}")

    def describe(self) -> Dict[str, Any]:
        return {
            "stepSeconds": self.step_seconds,
            "sampleHours": self.sample_hours,
            "windageOverride": self.windage,
            "regionBufferKm": self.region_buffer_km,
            "boundaryStride": self.boundary_stride,
            "confidenceSpreadReferenceKm": self.confidence_spread_reference_km,
        }


@dataclass
class OriginEstimate:
    """The hindcast result: a REGION (never a point), its window and confidence."""

    region_ring: List[Tuple[float, float]]          # closed [(lon, lat), ...]
    area_km2: float
    bounds: Dict[str, float]
    confidence: float
    spread_km: float
    release_window: ReleaseWindow
    observed_iso: str
    observed_epoch: int
    backdrift_path: List[Tuple[float, float]]       # [(lat, lon), ...] for visualisation
    drift: Dict[str, Any]
    seed_count: int
    sample_count: int
    field_summary: Dict[str, Any]
    notes: List[str] = dataclass_field(default_factory=list)
    warnings: List[str] = dataclass_field(default_factory=list)

    def region_contains(self, lat: float, lon: float) -> bool:
        """True when a position is inside the hull OR within the safety buffer."""
        if point_in_ring(lon, lat, self.region_ring):
            return True
        return distance_to_ring_km(lat, lon, self.region_ring) <= float(
            self.drift.get("regionBufferKm", 0.0))

    def distance_to_region_km(self, lat: float, lon: float) -> float:
        """0.0 when inside the region; otherwise the distance to its edges."""
        if self.region_contains(lat, lon):
            return 0.0
        return distance_to_ring_km(lat, lon, self.region_ring)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-ready result. NOTE: there is deliberately no point-estimate field."""
        return {
            "region": {
                "geometry": {"type": "Polygon",
                             "coordinates": [[list(p) for p in self.region_ring]]},
                "areaKm2": round(self.area_km2, 3),
                "bounds": self.bounds,
                "confidence": round(self.confidence, 3),
                "spreadKm": round(self.spread_km, 3),
                "vertexCount": len(self.region_ring),
                "method": (
                    "backward particle drift of the observed slick across the candidate "
                    "release window; convex hull of particle snapshots"
                ),
                "notes": [
                    "the origin is reported as a REGION, never a single point",
                    "confidence reflects internal spread of this prototype model, "
                    "not scientific accuracy",
                ],
            },
            "releaseWindow": {
                **self.release_window.describe(),
                "hoursBeforeObservation":
                    self.release_window.hours_before(self.observed_epoch),
                "note": (
                    "candidate-window prior supplied with the case; the region itself is "
                    "reconstructed from the slick and the environmental field"
                ),
            },
            "observedAt": self.observed_iso,
            "drift": {
                **self.drift,
                "backdriftPath": [[round(lat, 6), round(lon, 6)]
                                  for lat, lon in self.backdrift_path],
                "field": dict(self.field_summary),
            },
            "seedCount": self.seed_count,
            "sampleCount": self.sample_count,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
        }


def estimate_origin(
    slick_ring: Sequence[Tuple[float, float]],
    observed_iso: str,
    window: ReleaseWindow,
    field: EnvironmentalField,
    config: Optional[OriginConfig] = None,
) -> OriginEstimate:
    """Backward-drift the observed slick into an origin REGION.

    `slick_ring` is the slick polygon as [(lon, lat), ...] (GeoJSON order, a
    closing duplicate tolerated). Raises OriginHindcastError when the cloud
    cannot form a polygon - a degenerate region must fail loudly rather than
    collapse into an implicit point estimate.
    """
    cfg = config or OriginConfig()
    observed_dt = parse_iso_z(observed_iso)
    observed_epoch = int(observed_dt.timestamp())
    if window.end_epoch > observed_epoch:
        raise OriginHindcastError(
            f"release window {window.start_iso}..{window.end_iso} ends after the "
            f"observation {observed_iso}; a backward drift needs a past window"
        )

    ring = [(float(p[0]), float(p[1])) for p in slick_ring]
    if ring and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        raise OriginHindcastError(f"slick ring needs at least 3 vertices, got {len(ring)}")

    # Seed particles: slick centroid plus every Nth boundary vertex, so the
    # cloud inherits both the slick's extent and its orientation.
    centroid_lon = sum(p[0] for p in ring) / len(ring)
    centroid_lat = sum(p[1] for p in ring) / len(ring)
    seeds: List[List[float]] = [[centroid_lat, centroid_lon]]
    for k in range(0, len(ring), cfg.boundary_stride):
        lon, lat = ring[k]
        seeds.append([lat, lon])

    step = cfg.step_seconds
    sample_every = max(1, int(round(cfg.sample_hours * 3600.0 / step)))
    total_steps = int(round((observed_epoch - window.start_epoch) / step))
    if total_steps < 1:
        raise OriginHindcastError(
            "candidate release window leaves no time to integrate before the observation"
        )

    snapshots: List[Tuple[float, float]] = []     # (lon, lat) inside the window
    edge_end: List[Tuple[float, float]] = []       # nearest snapshot at/before window end
    edge_end_captured = False
    backdrift_path: List[Tuple[float, float]] = [(round(centroid_lat, 6),
                                                  round(centroid_lon, 6))]

    for i in range(1, total_steps + 1):
        for particle in seeds:
            particle[0], particle[1] = field.drift_step(
                particle[0], particle[1], -step, windage=cfg.windage)
        epoch_now = observed_epoch - i * step
        if not edge_end_captured and epoch_now <= window.end_epoch:
            edge_end_captured = True
            edge_end = [(round(p[1], 6), round(p[0], 6)) for p in seeds]
        if i % sample_every == 0 or i == total_steps:
            if window.contains(epoch_now):
                snapshots.extend((round(p[1], 6), round(p[0], 6)) for p in seeds)
            if i % sample_every == 0:
                backdrift_path.append((round(seeds[0][0], 6), round(seeds[0][1], 6)))

    warnings: List[str] = []
    if not snapshots and edge_end:
        # Window edges not aligned with the sampling grid: fall back to the two
        # bracketing snapshots instead of returning nothing.
        warnings.append(
            "no particle snapshot aligned exactly with the release window; used the "
            "bracketing hindcast positions instead"
        )
        snapshots = edge_end + [(round(p[1], 6), round(p[0], 6)) for p in seeds]
    if len(snapshots) < 4:
        raise OriginHindcastError(
            f"particle cloud too small to form a region ({len(snapshots)} positions)"
        )

    hull = [(round(lon, 6), round(lat, 6)) for lon, lat in convex_hull(snapshots)]
    if len(hull) < 4:
        raise OriginHindcastError("convex hull of the particle cloud is degenerate")

    area_km2 = polygon_area_km2(hull)
    lats = [p[1] for p in hull]
    lons = [p[0] for p in hull]
    bounds = {"minLat": round(min(lats), 6), "maxLat": round(max(lats), 6),
              "minLon": round(min(lons), 6), "maxLon": round(max(lons), 6)}

    mean_lat = sum(p[1] for p in snapshots) / len(snapshots)
    mean_lon = sum(p[0] for p in snapshots) / len(snapshots)
    cos_lat = max(math.cos(math.radians(mean_lat)), 1e-6)
    spread_sum = 0.0
    for lon, lat in snapshots:
        dx = math.radians(lon - mean_lon) * 6371.0088 * cos_lat
        dy = math.radians(lat - mean_lat) * 6371.0088
        spread_sum += dx * dx + dy * dy
    spread_km = math.sqrt(spread_sum / len(snapshots))
    confidence = _clamp(1.0 - spread_km / cfg.confidence_spread_reference_km, 0.05, 0.99)

    warnings.extend(w for w in field.warnings if w not in warnings)
    windage_used = cfg.windage if cfg.windage is not None else field.windage
    drift_meta: Dict[str, Any] = {
        "windageCoefficient": windage_used,
        "windageSource": ("OriginConfig override" if cfg.windage is not None
                          else "environmental field"),
        "stepSeconds": step,
        "sampleHours": cfg.sample_hours,
        "regionBufferKm": cfg.region_buffer_km,
        "integration": "backward Euler (dt < 0) of surface current + windage * wind",
        "parametersArePrototypeValues": True,
        "config": cfg.describe(),
    }
    notes = [
        "particles are the observed slick integrated backwards across the "
        "candidate release window; the region is their convex hull",
        "prototype drift model - not a validated ocean model (docs/methodology.md)",
        f"candidate window provenance: {window.source}",
    ]
    field_summary = {
        "provider": field.provider,
        "synthetic": field.synthetic,
        "datasetLabel": field.dataset_label,
        "timeBehaviour": field.time_behaviour,
        "windageCoefficient": field.windage,
    }

    return OriginEstimate(
        region_ring=hull,
        area_km2=area_km2,
        bounds=bounds,
        confidence=round(confidence, 3),
        spread_km=round(spread_km, 3),
        release_window=window,
        observed_iso=observed_iso,
        observed_epoch=observed_epoch,
        backdrift_path=backdrift_path,
        drift=drift_meta,
        seed_count=len(seeds),
        sample_count=len(snapshots),
        field_summary=field_summary,
        notes=notes,
        warnings=warnings,
    )