"""Bidirectional drift simulation engine for ABYSS forensic intelligence.

Supports:
- Forward simulation (release -> forecast footprint)
- Backward simulation (observed slick -> probable origin)
- Multiple windage ensemble for uncertainty envelope
- Strict observation_time requirement (never fabricates timestamps)
- Provenance recording
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.hindcast.environmental import EnvironmentalField


@dataclass
class TrajectoryPoint:
    lat: float
    lon: float
    elapsed_seconds: float
    timestamp_iso: Optional[str] = None


@dataclass
class ParticleTrajectory:
    particle_id: int
    windage: float
    direction: str  # "forward" or "backward"
    points: List[TrajectoryPoint]
    final_lat: float
    final_lon: float


@dataclass
class DriftResult:
    direction: str
    reference_time_iso: str
    duration_hours: float
    step_seconds: float
    trajectories: List[ParticleTrajectory]
    centroid: Tuple[float, float]
    spread_radius_km: float
    uncertainty_polygon: List[Tuple[float, float]]
    windage_ensemble: List[float]
    provenance: Dict[str, Any]
    notes: List[str] = dc_field(default_factory=list)
    warnings: List[str] = dc_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction,
            "reference_time_iso": self.reference_time_iso,
            "duration_hours": self.duration_hours,
            "step_seconds": self.step_seconds,
            "particle_count": len(self.trajectories),
            "centroid": {"lat": self.centroid[0], "lon": self.centroid[1]},
            "spread_radius_km": round(self.spread_radius_km, 3),
            "uncertainty_polygon": [[lat, lon] for lat, lon in self.uncertainty_polygon],
            "windage_ensemble": list(self.windage_ensemble),
            "trajectories": [
                {
                    "particle_id": t.particle_id,
                    "windage": t.windage,
                    "direction": t.direction,
                    "final_point": {"lat": t.final_lat, "lon": t.final_lon},
                    "point_count": len(t.points),
                    "path": [{"lat": p.lat, "lon": p.lon, "t_sec": p.elapsed_seconds} for p in t.points],
                }
                for t in self.trajectories
            ],
            "provenance": dict(self.provenance),
            "notes": list(self.notes),
            "warnings": list(self.warnings),
        }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def compute_uncertainty_circle(
    center_lat: float, center_lon: float, radius_km: float, n_points: int = 16
) -> List[Tuple[float, float]]:
    """Compute circular polygon approximation for uncertainty envelope."""
    r_earth = 6371.0
    ring: List[Tuple[float, float]] = []
    lat_r = math.radians(center_lat)
    lon_r = math.radians(center_lon)
    d_r = radius_km / r_earth

    for i in range(n_points):
        theta = 2.0 * math.pi * i / n_points
        lat_pt = math.asin(
            math.sin(lat_r) * math.cos(d_r) + math.cos(lat_r) * math.sin(d_r) * math.cos(theta)
        )
        lon_pt = lon_r + math.atan2(
            math.sin(theta) * math.sin(d_r) * math.cos(lat_r),
            math.cos(d_r) - math.sin(lat_r) * math.sin(lat_pt),
        )
        ring.append((round(math.degrees(lat_pt), 6), round(math.degrees(lon_pt), 6)))
    # Close ring
    ring.append(ring[0])
    return ring


def run_drift_simulation(
    field: EnvironmentalField,
    origin_lat: float,
    origin_lon: float,
    reference_time_iso: Optional[str],
    direction: str = "backward",  # "backward" or "forward"
    duration_hours: float = 6.0,
    step_seconds: float = 300.0,
    windage_ensemble: Optional[Sequence[float]] = None,
    provenance_meta: Optional[Dict[str, Any]] = None,
) -> DriftResult:
    """Run bidirectional particle drift simulation using EnvironmentalField.

    Raises ValueError if reference_time_iso is missing or empty.
    """
    if not reference_time_iso or not reference_time_iso.strip():
        raise ValueError(
            "observation_time / release_time is REQUIRED. "
            "ABYSS refuses to simulate drift without an explicit timestamp."
        )

    direction = direction.lower().strip()
    if direction not in ("backward", "forward"):
        raise ValueError(f"Direction must be 'backward' or 'forward', got: {direction}")

    if duration_hours <= 0:
        raise ValueError("duration_hours must be positive")

    # Time step sign: backward uses negative time steps
    dt = -abs(step_seconds) if direction == "backward" else abs(step_seconds)
    total_seconds = duration_hours * 3600.0
    n_steps = int(math.ceil(total_seconds / abs(dt)))

    if windage_ensemble is None:
        # Default ensemble covering typical oil windage range
        windage_ensemble = [0.02, 0.035, 0.05]

    trajectories: List[ParticleTrajectory] = []
    pid = 0

    # Seed positions: center + 4 cardinal perturbations (50m offset)
    dlat_seed = 0.0005
    dlon_seed = 0.0005
    seeds = [
        (origin_lat, origin_lon),
        (origin_lat + dlat_seed, origin_lon),
        (origin_lat - dlat_seed, origin_lon),
        (origin_lat, origin_lon + dlon_seed),
        (origin_lat, origin_lon - dlon_seed),
    ]

    for windage in windage_ensemble:
        for s_lat, s_lon in seeds:
            pid += 1
            cur_lat, cur_lon = s_lat, s_lon
            points: List[TrajectoryPoint] = [
                TrajectoryPoint(lat=cur_lat, lon=cur_lon, elapsed_seconds=0.0)
            ]
            for step_idx in range(1, n_steps + 1):
                cur_lat, cur_lon = field.drift_step(
                    cur_lat, cur_lon, dt_seconds=dt, windage=windage
                )
                points.append(
                    TrajectoryPoint(
                        lat=round(cur_lat, 6),
                        lon=round(cur_lon, 6),
                        elapsed_seconds=round(step_idx * dt, 1),
                    )
                )

            trajectories.append(
                ParticleTrajectory(
                    particle_id=pid,
                    windage=windage,
                    direction=direction,
                    points=points,
                    final_lat=round(cur_lat, 6),
                    final_lon=round(cur_lon, 6),
                )
            )

    # Compute endpoint centroid
    final_lats = [t.final_lat for t in trajectories]
    final_lons = [t.final_lon for t in trajectories]
    c_lat = sum(final_lats) / len(final_lats)
    c_lon = sum(final_lons) / len(final_lons)

    # Compute spread (max distance from centroid)
    spread = max(haversine_km(c_lat, c_lon, flat, flon) for flat, flon in zip(final_lats, final_lons))
    # Minimum radius 0.5 km for visualization
    radius_km = max(spread, 0.5)

    uncertainty_ring = compute_uncertainty_circle(c_lat, c_lon, radius_km)

    prov = dict(provenance_meta or {})
    prov["model"] = "ABYSS Euler-Lagrangian transport"
    prov["time_step_seconds"] = dt
    prov["ensemble_size"] = len(trajectories)
    prov["windage_values"] = list(windage_ensemble)
    prov["direction"] = direction

    notes: List[str] = [
        f"Simulated {len(trajectories)} particles over {duration_hours:.1f}h using dt={dt}s",
        f"Centroid at ({c_lat:.5f}, {c_lon:.5f}) with spread radius {radius_km:.3f} km",
    ]
    if direction == "backward":
        notes.append("Backdrift endpoint represents relative origin likelihood field.")
    else:
        notes.append("Forward drift endpoint represents forecast footprint.")

    return DriftResult(
        direction=direction,
        reference_time_iso=reference_time_iso,
        duration_hours=duration_hours,
        step_seconds=dt,
        trajectories=trajectories,
        centroid=(round(c_lat, 6), round(c_lon, 6)),
        spread_radius_km=round(radius_km, 3),
        uncertainty_polygon=uncertainty_ring,
        windage_ensemble=list(windage_ensemble),
        provenance=prov,
        notes=notes,
    )
