"""ABYSS - spatial, temporal and trajectory compatibility (Phases 5-7).

PURPOSE
    For one vessel trajectory and the estimated origin region + release window,
    answer three separate questions, FACTS first and pass/fail annotations
    second:

    Phase 5 spatial     - how close did it get to the origin region, overall
                          and during the window? (kilometres, honest units)
    Phase 6 temporal    - was it inside the region DURING the window?
    Phase 7 trajectory  - is the observed movement physically plausible, and
                          does it actually pass through the region in time?

WHY FACTS BEFORE JUDGEMENT
    Distances and booleans are reported even when a filter fails: an
    investigator must see HOW FAR outside, not just "excluded". The suspicion
    scoring phase consumes these numbers; nothing here raises or lowers
    suspicion - it only measures.

DISTANCES ARE RELATIVE TO THE ESTIMATED REGION
    All distances measure to the hindcast region (including its positional
    buffer), never to any hidden truth. Inside -> 0.0 km by definition. Whole-
    track distance is reported alongside the window distance because "passes
    through the region but at the wrong time" is a distinct, reportable fact.

WHAT IT DOES NOT DO
    No scoring, no ranking, no gap relevance, no behavioural comparison - those
    are later phases with their own modules.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):  # executed directly as a script
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.ais.trajectory import VesselTrajectory
    from app.hindcast.origin import OriginEstimate
    from app.timeutils import ReleaseWindow, epoch_seconds
else:
    from app.ais.trajectory import VesselTrajectory
    from app.hindcast.origin import OriginEstimate
    from app.timeutils import ReleaseWindow, epoch_seconds

__all__ = ["CompatibilityError", "CompatibilityConfig", "CompatibilityAssessment",
           "assess_compatibility"]


class CompatibilityError(RuntimeError):
    """Raised when a trajectory cannot be assessed at all."""


@dataclass(frozen=True)
class CompatibilityConfig:
    """Thresholds for the Phase 5-7 filters. Prototype values, all reported."""

    spatial_falloff_km: float = 30.0        # spatial proximity reaches zero here
    trajectory_plausibility_floor: float = 0.9
    max_plausible_speed_kn: float = 60.0    # global ceiling (cleaning policy)
    speed_safety_factor: float = 1.5        # segment cap vs the vessel's own max
    min_speed_cap_kn: float = 5.0           # floor for slow vessels

    def __post_init__(self) -> None:
        if self.spatial_falloff_km <= 0:
            raise ValueError(f"spatial_falloff_km must be > 0, got {self.spatial_falloff_km}")
        if not (0.0 <= self.trajectory_plausibility_floor <= 1.0):
            raise ValueError("trajectory_plausibility_floor must be in [0, 1]")
        if self.max_plausible_speed_kn <= 0:
            raise ValueError("max_plausible_speed_kn must be > 0")
        if self.speed_safety_factor < 1.0:
            raise ValueError("speed_safety_factor must be >= 1.0")
        if self.min_speed_cap_kn <= 0:
            raise ValueError("min_speed_cap_kn must be > 0")

    def describe(self) -> Dict[str, Any]:
        return {
            "spatialFalloffKm": self.spatial_falloff_km,
            "trajectoryPlausibilityFloor": self.trajectory_plausibility_floor,
            "maxPlausibleSpeedKn": self.max_plausible_speed_kn,
            "speedSafetyFactor": self.speed_safety_factor,
            "minSpeedCapKn": self.min_speed_cap_kn,
        }


@dataclass
class CompatibilityAssessment:
    """Measured compatibility facts plus annotation-only pass/fail filters."""

    mmsi: str
    min_distance_km_during_window: Optional[float] = None
    min_distance_km_whole_track: float = float("inf")
    inside_region_during_window: bool = False
    inside_region_anytime: bool = False
    inside_region_relation: str = "never"   # during_window | before_window |
                                            # after_window | outside_window | never
    first_inside_timestamp: Optional[str] = None
    records_in_window: int = 0
    window_presence_seconds: int = 0     # time INSIDE the region while the window is open
    window_coverage_seconds: int = 0     # time the window is covered by any records at all
    segments_in_window: int = 0
    plausible_segments_in_window: int = 0
    plausible_segment_fraction: float = 0.0
    speed_cap_kn: float = 0.0
    movement_through_region: bool = False
    closest_in_window: Optional[Dict[str, Any]] = None
    spatial_pass: bool = False
    temporal_pass: bool = False
    trajectory_pass: bool = False
    notes: List[str] = dataclass_field(default_factory=list)
    warnings: List[str] = dataclass_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mmsi": self.mmsi,
            "minDistanceKmDuringWindow": (
                None if self.min_distance_km_during_window is None
                else round(self.min_distance_km_during_window, 3)),
            "minDistanceKmWholeTrack": round(self.min_distance_km_whole_track, 3),
            "insideRegionDuringWindow": self.inside_region_during_window,
            "insideRegionAnytime": self.inside_region_anytime,
            "insideRegionRelation": self.inside_region_relation,
            "firstInsideTimestamp": self.first_inside_timestamp,
            "recordsInWindow": self.records_in_window,
            "windowPresenceSeconds": self.window_presence_seconds,
            "windowCoverageSeconds": self.window_coverage_seconds,
            "segmentsInWindow": self.segments_in_window,
            "plausibleSegmentsInWindow": self.plausible_segments_in_window,
            "plausibleSegmentFraction": round(self.plausible_segment_fraction, 4),
            "speedCapKn": round(self.speed_cap_kn, 3),
            "movementThroughRegion": self.movement_through_region,
            "closestInWindow": self.closest_in_window,
            "filters": {"spatial": self.spatial_pass, "temporal": self.temporal_pass,
                        "trajectory": self.trajectory_pass},
            "notes": list(self.notes),
            "warnings": list(self.warnings),
        }


def assess_compatibility(
    trajectory: VesselTrajectory,
    origin: OriginEstimate,
    window: ReleaseWindow,
    config: Optional[CompatibilityConfig] = None,
) -> CompatibilityAssessment:
    """Measure Phases 5-7 compatibility of one trajectory against the estimate.

    Pure function of (trajectory, origin region, window): identical inputs give
    identical output, and no judgement beyond the configured thresholds is made.
    """
    cfg = config or CompatibilityConfig()
    if not trajectory.points:
        raise CompatibilityError(f"trajectory {trajectory.mmsi} has no points to assess")

    assessment = CompatibilityAssessment(mmsi=trajectory.mmsi)
    win_min: Optional[float] = None
    closest: Optional[Dict[str, Any]] = None
    whole_min = float("inf")
    inside_anytime = False
    inside_during = False
    first_inside_ts: Optional[str] = None
    inside_epochs: List[int] = []
    win_epochs: List[int] = []
    win_inside_epochs: List[int] = []
    epoch_by_ts: Dict[str, int] = {}

    for point in trajectory.points:
        epoch_by_ts.setdefault(point.timestamp, point.epochSeconds)
        distance = origin.distance_to_region_km(point.latitude, point.longitude)
        whole_min = min(whole_min, distance)
        if distance <= 0.0:
            inside_anytime = True
            inside_epochs.append(point.epochSeconds)
            if first_inside_ts is None:
                first_inside_ts = point.timestamp
        if window.contains(point.epochSeconds):
            win_epochs.append(point.epochSeconds)
            assessment.records_in_window += 1
            if win_min is None or distance < win_min:
                win_min = distance
                closest = {"timestamp": point.timestamp,
                           "lat": round(point.latitude, 6),
                           "lon": round(point.longitude, 6),
                           "distanceKm": round(distance, 3)}
            if distance <= 0.0:
                inside_during = True
                win_inside_epochs.append(point.epochSeconds)

    def _covered_seconds(epochs: List[int]) -> int:
        """Sum of intervals between CONSECUTIVE records - a measured span, not a guess."""
        total = 0
        previous: Optional[int] = None
        for epoch in sorted(epochs):
            if previous is not None and epoch > previous:
                total += epoch - previous
            previous = epoch
        return total

    # Two different questions, deliberately reported as two different numbers:
    # coverage = is the window observed at all (AIS availability), presence = was the
    # vessel actually inside the origin region (the Phase 6 temporal fact). Reporting
    # coverage under a "presence" name would claim location evidence the data never had.
    coverage = _covered_seconds(win_epochs)
    presence = _covered_seconds(win_inside_epochs)

    assessment.min_distance_km_during_window = win_min
    assessment.min_distance_km_whole_track = whole_min
    assessment.inside_region_during_window = inside_during
    assessment.inside_region_anytime = inside_anytime
    assessment.first_inside_timestamp = first_inside_ts
    assessment.closest_in_window = closest
    assessment.movement_through_region = inside_during
    assessment.window_presence_seconds = presence
    assessment.window_coverage_seconds = coverage

    if inside_during:
        assessment.inside_region_relation = "during_window"
    elif inside_anytime:
        if min(inside_epochs) > window.end_epoch:
            assessment.inside_region_relation = "after_window"
        elif max(inside_epochs) < window.start_epoch:
            assessment.inside_region_relation = "before_window"
        else:
            assessment.inside_region_relation = "outside_window"
    else:
        assessment.inside_region_relation = "never"

    # Phase 7: observed segments starting inside the window must be plausible.
    own_max = trajectory.stats.get("maxReportedSogKn")
    if own_max:
        speed_cap = min(cfg.max_plausible_speed_kn,
                        max(float(own_max) * cfg.speed_safety_factor, cfg.min_speed_cap_kn))
    else:
        speed_cap = cfg.max_plausible_speed_kn
    assessment.speed_cap_kn = speed_cap

    for segment in trajectory.segments:
        start_epoch = epoch_by_ts.get(segment.startTimestamp)
        if start_epoch is None:
            start_epoch = epoch_seconds(segment.startTimestamp)
        if not window.contains(start_epoch):
            continue
        assessment.segments_in_window += 1
        speed = segment.impliedSpeedKn
        if speed is None or speed <= speed_cap:
            assessment.plausible_segments_in_window += 1

    if assessment.segments_in_window:
        assessment.plausible_segment_fraction = (
            assessment.plausible_segments_in_window / assessment.segments_in_window)
    else:
        assessment.warnings.append(
            "no observed segments start inside the release window")

    assessment.spatial_pass = (win_min is not None
                               and win_min <= cfg.spatial_falloff_km)
    assessment.temporal_pass = inside_during
    assessment.trajectory_pass = (assessment.segments_in_window > 0
                                  and assessment.plausible_segment_fraction
                                  >= cfg.trajectory_plausibility_floor)
    assessment.notes = [
        "distances are to the ESTIMATED origin region (with positional buffer), "
        "never to any hidden truth",
        "pass/fail flags annotate the facts; points are assigned by the evidence engine",
        "windowPresenceSeconds counts time INSIDE the region while the window was open; "
        "windowCoverageSeconds counts time the window is covered by records at all "
        "(AIS availability) - the two are deliberately separate measurements",
        f"config: {cfg.describe()}",
    ]
    return assessment