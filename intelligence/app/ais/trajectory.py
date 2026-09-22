"""ABYSS - AIS trajectory construction (Phase 4).

PURPOSE
    Turn the cleaned, time-ordered AIS records of Phase 3 into one VesselTrajectory per
    vessel: ordered positions, geodesic segment metrics, the structural gap list,
    stop/slow periods, significant course changes and GeoJSON geometry.

WHY IT IS NEEDED
    Every later step reasons about MOVEMENT, not about isolated points: spatial and
    temporal compatibility (Phases 5-6), trajectory feasibility (Phase 7), behaviour
    (Phase 8) and gap analysis (Phase 9) all need per-vessel ordered tracks built with
    honest, traceable metrics.

SCOPE BOUNDARIES - WHAT THIS MODULE DOES NOT DO
    * It does NOT analyse gaps. It reports that an interval contains no records, how long
      it is, the positions either side and the straight-line implied speed. Whether a gap
      is RELEVANT (could the vessel have crossed the origin region?) is Phase 9, and a gap
      alone never implies suspicion (docs/methodology.md section 5).
    * It does NOT compare a vessel with its own behavioural baseline (Phase 8). Stop and
      slow periods reported here are DESCRIPTIVE: legitimate traffic produces them too.
    * It does NOT filter candidate vessels (Phases 5-7) and does NOT score anything
      (Phase 10).
    * It never concludes anything about a vessel.

GEODESY
    Distances are great-circle (haversine) distances and courses are initial great-circle
    bearings, both from `app.geo` - never planar Euclidean arithmetic.

WHAT COUNTS AS TRAVEL
    Distance is summed over CONTIGUOUS RUNS of records only. The straight line across a
    gap is reported separately (`straightLineGapKm`) and is NOT counted as observed
    travel, because that movement was never observed.

COVERAGE EDGES
    A vessel's first and last record have no bracketing neighbour, so the absence of
    records before/after them cannot be measured. Those edges are reported as
    `startsAtExtractBoundary` / `endsAtExtractBoundary` when they coincide (within the gap
    threshold) with the start/end of the whole extract, so that a later phase does not
    mistake an area-scoped extract edge for an AIS transmission gap.

DETERMINISM
    Pure arithmetic over the supplied records: identical input gives identical output.

CLI
    cd intelligence
    ../.venv/bin/python -m app.ais.trajectory                  # clean demo case, build tracks
    ../.venv/bin/python -m app.ais.trajectory --json /tmp/tracks.json
    ../.venv/bin/python -m app.ais.trajectory --gap-threshold-minutes 15 --quiet
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

if __package__ in (None, ""):  # executed directly as a script
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.ais.cleaning import CleaningResult, clean_csv, clean_demo_case
    from app.geo import KNOTS_TO_KMH, haversine_km, implied_speed_kn, initial_bearing_deg
else:
    from app.ais.cleaning import CleaningResult, clean_csv, clean_demo_case
    from app.geo import KNOTS_TO_KMH, haversine_km, implied_speed_kn, initial_bearing_deg

MODULE_VERSION = "1.0.0"

__all__ = [
    "TrajectoryConfig", "TrajectoryPoint", "TrajectorySegment", "TrajectoryGap",
    "StopSlowPeriod", "CourseChangeEvent", "VesselTrajectory", "TrajectoryCollection",
    "build_trajectories", "build_trajectories_from_cleaning", "trajectory_from_records",
    "print_trajectory_summary",
]


class AisTrajectoryError(RuntimeError):
    """Raised when the input cannot be turned into trajectories at all."""


@dataclass(frozen=True)
class TrajectoryConfig:
    """Configurable thresholds for trajectory construction.

    Every value here is a PROTOTYPE threshold, not a scientific constant: they are
    reported with the output so a reviewer can see exactly what was applied, and they
    can be changed per dataset. The AIS reporting interval of a real feed determines a
    sensible gap threshold; the values below suit the synthetic CASE-001 extract.
    """

    gap_threshold_seconds: float = 1800.0
    stop_speed_kn: float = 0.5
    slow_speed_kn: float = 3.0
    min_period_seconds: float = 600.0
    min_period_records: int = 2
    course_change_threshold_deg: float = 30.0
    min_speed_for_course_change_kn: float = 1.0
    max_plausible_speed_kn: float = 60.0

    def __post_init__(self) -> None:
        if self.gap_threshold_seconds <= 0:
            raise ValueError("gap_threshold_seconds must be > 0")
        if not (0.0 <= self.stop_speed_kn < self.slow_speed_kn):
            raise ValueError("stop_speed_kn must be >= 0 and < slow_speed_kn")
        if self.min_period_seconds < 0 or self.min_period_records < 1:
            raise ValueError("period thresholds must be >= 0 and >= 1 record")
        if not (0.0 < self.course_change_threshold_deg <= 180.0):
            raise ValueError("course_change_threshold_deg must be in (0, 180]")
        if self.min_speed_for_course_change_kn < 0:
            raise ValueError("min_speed_for_course_change_kn must be >= 0")
        if self.max_plausible_speed_kn <= 0:
            raise ValueError("max_plausible_speed_kn must be > 0")

    def describe(self) -> Dict[str, Any]:
        return {
            "gapThresholdSeconds": self.gap_threshold_seconds,
            "stopSpeedKn": self.stop_speed_kn,
            "slowSpeedKn": self.slow_speed_kn,
            "minPeriodSeconds": self.min_period_seconds,
            "minPeriodRecords": self.min_period_records,
            "courseChangeThresholdDeg": self.course_change_threshold_deg,
            "minSpeedForCourseChangeKn": self.min_speed_for_course_change_kn,
            "maxPlausibleSpeedKn": self.max_plausible_speed_kn,
            "prototypeThresholds": True,
        }


# ---------------------------------------------------------------------------
# Trajectory components
# ---------------------------------------------------------------------------
@dataclass
class TrajectoryPoint:
    """One ordered position with its reported and recorded metadata."""

    index: int
    timestamp: str
    epochSeconds: int
    latitude: float
    longitude: float
    sogKn: Optional[float]
    cogDeg: Optional[float]
    headingDeg: Optional[int]
    navigationStatus: Optional[int]
    sourceLine: int
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index, "timestamp": self.timestamp, "epochSeconds": self.epochSeconds,
            "latitude": self.latitude, "longitude": self.longitude, "sogKn": self.sogKn,
            "cogDeg": self.cogDeg, "headingDeg": self.headingDeg,
            "navigationStatus": self.navigationStatus, "sourceLine": self.sourceLine,
            "warnings": list(self.warnings),
        }


@dataclass
class TrajectorySegment:
    """Movement between two CONSECUTIVE records (never across a gap)."""

    fromIndex: int
    toIndex: int
    startTimestamp: str
    endTimestamp: str
    elapsedSeconds: float
    distanceKm: float
    impliedSpeedKn: Optional[float]
    bearingDeg: float
    # Speed over ground REPORTED AT THE START OF THIS INTERVAL (fromIndex).
    # AIS semantics matter here: a position report states the speed the vessel is
    # making at that instant, which describes the travel from that instant onwards.
    # Taking the destination record's speed instead mispairs every step where the
    # vessel changes speed, which for this demo dataset produced steps whose ground
    # speed was 3.5x the "reported" value - enough to corrupt trajectory
    # compatibility and AIS gap feasibility in later phases.
    reportedSogKn: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fromIndex": self.fromIndex, "toIndex": self.toIndex,
            "startTimestamp": self.startTimestamp, "endTimestamp": self.endTimestamp,
            "elapsedSeconds": round(self.elapsedSeconds, 3),
            "distanceKm": round(self.distanceKm, 6),
            "impliedSpeedKn": None if self.impliedSpeedKn is None else round(self.impliedSpeedKn, 3),
            "bearingDeg": round(self.bearingDeg, 3),
            "reportedSogKn": self.reportedSogKn,
        }


@dataclass
class TrajectoryGap:
    """A structural interval with no records. Carries facts only - no judgement.

    Whether this gap is compatible with a reconstructed origin region and release window
    is decided in Phase 9, and a gap alone never raises suspicion.
    """

    startTimestamp: str
    endTimestamp: str
    durationSeconds: float
    lastPosition: Dict[str, Any]
    nextPosition: Dict[str, Any]
    straightLineKm: float
    impliedSpeedKn: Optional[float]
    initialBearingDeg: float
    impliedSpeedExceedsConfiguredMaximum: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "startTimestamp": self.startTimestamp, "endTimestamp": self.endTimestamp,
            "durationSeconds": round(self.durationSeconds, 3),
            "durationHours": round(self.durationSeconds / 3600.0, 4),
            "lastPosition": self.lastPosition, "nextPosition": self.nextPosition,
            "straightLineKm": round(self.straightLineKm, 6),
            "impliedSpeedKn": None if self.impliedSpeedKn is None else round(self.impliedSpeedKn, 3),
            "initialBearingDeg": round(self.initialBearingDeg, 3),
            "impliedSpeedExceedsConfiguredMaximum": self.impliedSpeedExceedsConfiguredMaximum,
            "note": "structural fact only; relevance is assessed in the AIS gap analysis phase",
        }


@dataclass
class StopSlowPeriod:
    """A DESCRIPTIVE period of low speed. Legitimate traffic produces these too."""

    kind: str  # "stop" or "slow"
    startTimestamp: str
    endTimestamp: str
    durationSeconds: float
    recordCount: int
    minSogKn: Optional[float]
    meanSogKn: Optional[float]
    centroidLatitude: float
    centroidLongitude: float
    startIndex: int
    endIndex: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind, "startTimestamp": self.startTimestamp, "endTimestamp": self.endTimestamp,
            "durationSeconds": round(self.durationSeconds, 3),
            "durationMinutes": round(self.durationSeconds / 60.0, 3),
            "recordCount": self.recordCount,
            "minSogKn": None if self.minSogKn is None else round(self.minSogKn, 3),
            "meanSogKn": None if self.meanSogKn is None else round(self.meanSogKn, 3),
            "centroid": {"lat": round(self.centroidLatitude, 6), "lon": round(self.centroidLongitude, 6)},
            "startIndex": self.startIndex, "endIndex": self.endIndex,
            "note": "descriptive only; the behavioural baseline comparison is a later phase",
        }


@dataclass
class CourseChangeEvent:
    """A significant change of derived course between two consecutive segments."""

    index: int
    timestamp: str
    latitude: float
    longitude: float
    fromBearingDeg: float
    toBearingDeg: float
    changeDeg: float          # signed, in (-180, 180]
    absoluteChangeDeg: float
    speedKn: Optional[float]  # reported SOG at the junction when available
    sourceLine: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index, "timestamp": self.timestamp,
            "latitude": round(self.latitude, 6), "longitude": round(self.longitude, 6),
            "fromBearingDeg": round(self.fromBearingDeg, 3), "toBearingDeg": round(self.toBearingDeg, 3),
            "changeDeg": round(self.changeDeg, 3),
            "absoluteChangeDeg": round(self.absoluteChangeDeg, 3),
            "speedKn": self.speedKn, "sourceLine": self.sourceLine,
        }


@dataclass
class VesselTrajectory:
    """One vessel's ordered track plus descriptive metrics, gaps and events.

    Numeric summaries live in `stats` (JSON-ready) and are named explicitly there.
    Nothing in this object asserts that a vessel did anything wrong.
    """

    mmsi: str
    imo: Optional[str]
    vesselName: Optional[str]
    vesselType: Optional[int]
    datasetLabel: Optional[str]
    synthetic: bool
    points: List[TrajectoryPoint] = field(default_factory=list)
    segments: List[TrajectorySegment] = field(default_factory=list)
    gaps: List[TrajectoryGap] = field(default_factory=list)
    stopSlowPeriods: List[StopSlowPeriod] = field(default_factory=list)
    courseChanges: List[CourseChangeEvent] = field(default_factory=list)
    geometry: Optional[Dict[str, Any]] = None
    geometryByLeg: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    # Convenience accessors used by later phases and tests.
    @property
    def record_count(self) -> int:
        return len(self.points)

    @property
    def first_timestamp(self) -> Optional[str]:
        return self.points[0].timestamp if self.points else None

    @property
    def last_timestamp(self) -> Optional[str]:
        return self.points[-1].timestamp if self.points else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mmsi": self.mmsi,
            "imo": self.imo,
            "vesselName": self.vesselName,
            "vesselType": self.vesselType,
            "datasetLabel": self.datasetLabel,
            "synthetic": self.synthetic,
            "stats": self.stats,
            "warnings": list(self.warnings),
            "points": [point.to_dict() for point in self.points],
            "segments": [segment.to_dict() for segment in self.segments],
            "gaps": [gap.to_dict() for gap in self.gaps],
            "stopSlowPeriods": [period.to_dict() for period in self.stopSlowPeriods],
            "courseChanges": [event.to_dict() for event in self.courseChanges],
            "geometry": self.geometry,
            "geometryByLeg": self.geometryByLeg,
        }


@dataclass
class TrajectoryCollection:
    """All trajectories for one investigation area, plus fleet-level statistics."""

    trajectories: List[VesselTrajectory] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    source: Dict[str, Any] = field(default_factory=dict)
    skippedRecords: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def synthetic(self) -> bool:
        return bool(self.source.get("synthetic"))

    def by_mmsi(self) -> Dict[str, VesselTrajectory]:
        return {trajectory.mmsi: trajectory for trajectory in self.trajectories}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": "ais.trajectory",
            "moduleVersion": MODULE_VERSION,
            "dataSource": self.source.get("provider", "unknown"),
            "synthetic": self.synthetic,
            "source": self.source,
            "config": self.config,
            "counts": self.statistics.get("counts", {}),
            "statistics": self.statistics,
            "warnings": self.warnings,
            "notes": self.notes,
            "skippedRecords": self.skippedRecords,
            "trajectories": [trajectory.to_dict() for trajectory in self.trajectories],
        }


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------
_REQUIRED_METADATA_KEYS = ("mmsi", "latitude", "longitude")


def _first(record: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
    return None


def _epoch_from_timestamp(value: Any) -> Optional[int]:
    """Fallback epoch resolution for records that carry only an ISO-8601 timestamp."""
    import datetime as _datetime

    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(_datetime.datetime.strptime(value, fmt).replace(
                tzinfo=_datetime.timezone.utc).timestamp())
        except ValueError:
            continue
    return None


def _normalise_records(
    records: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """Group usable records by vessel identifier and report the rest.

    Records that cannot be used are returned under `skipped` with a reason - the same
    principle as Phase 3 cleaning: nothing disappears without a trace.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    skipped: List[Dict[str, Any]] = []
    for position, record in enumerate(records):
        mmsi = str(_first(record, "mmsi", "MMSI") or "").strip()
        latitude = _first(record, "latitude", "lat")
        longitude = _first(record, "longitude", "lon")
        timestamp = _first(record, "timestamp")
        epoch = _first(record, "epochSeconds")
        if epoch is None:
            epoch = _epoch_from_timestamp(timestamp)

        reason: Optional[str] = None
        if not mmsi:
            reason = "missing vessel identifier"
        elif latitude is None or longitude is None:
            reason = "missing position"
        elif not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            reason = "non-numeric position"
        elif not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
            reason = "position out of range"
        elif epoch is None:
            reason = "missing or unparseable timestamp"
        if reason is not None:
            skipped.append({"inputIndex": position, "mmsi": mmsi or None, "reason": reason})
            continue

        sog = _first(record, "sogKn", "SOG", "sog")
        cog = _first(record, "cogDeg", "COG", "cog")
        heading = _first(record, "headingDeg", "heading")
        nav_status = _first(record, "navigationStatus")
        grouped.setdefault(mmsi, []).append({
            "mmsi": mmsi,
            "imo": _first(record, "imo", "IMO"),
            "vesselName": _first(record, "vesselName", "name"),
            "vesselType": _first(record, "vesselType"),
            "datasetLabel": _first(record, "datasetLabel"),
            "synthetic": bool(_first(record, "synthetic") or False),
            "timestamp": str(timestamp) if timestamp else None,
            "epochSeconds": int(epoch),
            "latitude": float(latitude),
            "longitude": float(longitude),
            "sogKn": None if sog is None else float(sog),
            "cogDeg": None if cog is None else float(cog),
            "headingDeg": None if heading is None else int(heading),
            "navigationStatus": None if nav_status is None else int(nav_status),
            "sourceLine": int(_first(record, "sourceLine") or 0),
            "warnings": list(_first(record, "warnings") or []),
        })
    return grouped, skipped


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------
def _signed_angle_delta(from_deg: float, to_deg: float) -> float:
    """Signed turn from one course to another, in (-180, 180].

    A 180 degree turn is reported as +180; its direction is genuinely ambiguous because
    a vessel could have turned either way.
    """
    delta = (to_deg - from_deg + 180.0) % 360.0 - 180.0
    return 180.0 if delta == -180.0 else delta


def _median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _both_at_least(first: Optional[float], second: Optional[float], threshold: float) -> bool:
    """True only when BOTH speeds are known and at or above the threshold.

    Unknown speeds (None) are never treated as "fast" or "slow": they simply do not
    qualify, so an unknown-speed junction cannot raise a course-change event.
    """
    if first is None or second is None:
        return False
    return first >= threshold and second >= threshold


def _position_dict(point: TrajectoryPoint) -> Dict[str, Any]:
    return {
        "latitude": round(point.latitude, 6), "longitude": round(point.longitude, 6),
        "timestamp": point.timestamp, "sogKn": point.sogKn, "sourceLine": point.sourceLine,
    }


# ---------------------------------------------------------------------------
# Low-speed period detection (descriptive, gap-aware)
# ---------------------------------------------------------------------------
def _speed_level(speed: Optional[float], config: TrajectoryConfig) -> Optional[int]:
    """Classify one speed: 2 = stopped, 1 = slow, 0 = moving, None = unknown.

    Unknown speeds are never guessed: they end the current period rather than extending
    it, so every reported period is backed by records that genuinely reported a low speed.
    """
    if speed is None:
        return None
    if speed < config.stop_speed_kn:
        return 2
    if speed < config.slow_speed_kn:
        return 1
    return 0


def _close_period(
    points: Sequence[TrajectoryPoint], run: Sequence[int], level: Optional[int],
    config: TrajectoryConfig,
) -> List[StopSlowPeriod]:
    """Turn one run of low-speed points into a reportable period, or nothing."""
    if level is None or len(run) < config.min_period_records:
        return []
    start_point, end_point = points[run[0]], points[run[-1]]
    duration = float(end_point.epochSeconds - start_point.epochSeconds)
    if duration < config.min_period_seconds:
        return []
    speeds = [points[index].sogKn for index in run if points[index].sogKn is not None]
    mean_speed = (sum(speeds) / len(speeds)) if speeds else None
    return [StopSlowPeriod(
        kind=("stop" if level == 2 else "slow"),
        startTimestamp=start_point.timestamp,
        endTimestamp=end_point.timestamp,
        durationSeconds=duration,
        recordCount=len(run),
        minSogKn=min(speeds) if speeds else None,
        meanSogKn=mean_speed,
        centroidLatitude=sum(points[index].latitude for index in run) / len(run),
        centroidLongitude=sum(points[index].longitude for index in run) / len(run),
        startIndex=run[0],
        endIndex=run[-1],
    )]


def _detect_stop_slow_periods(
    points: Sequence[TrajectoryPoint], legs: Sequence[Sequence[int]], config: TrajectoryConfig,
) -> List[StopSlowPeriod]:
    """Find low-speed periods. Runs never span a gap, because a gap is unobserved time."""
    periods: List[StopSlowPeriod] = []
    for leg in legs:
        run: List[int] = []
        run_level: Optional[int] = None
        for index in leg:
            level = _speed_level(points[index].sogKn, config)
            if level is None or level == 0:
                periods.extend(_close_period(points, run, run_level, config))
                run, run_level = [], None
                continue
            if run_level is not None and level != run_level:
                periods.extend(_close_period(points, run, run_level, config))
                run, run_level = [], None
            run.append(index)
            if run_level is None:
                run_level = level
        periods.extend(_close_period(points, run, run_level, config))
    periods.sort(key=lambda period: (period.startTimestamp, period.kind))
    return periods


def _detect_course_changes(
    points: Sequence[TrajectoryPoint], segments: Sequence[TrajectorySegment], config: TrajectoryConfig,
) -> Tuple[List[CourseChangeEvent], float, float]:
    """Flag significant turns between ADJACENT segments and total turn observed."""
    events: List[CourseChangeEvent] = []
    total_change = 0.0
    max_change = 0.0
    for position in range(1, len(segments)):
        first, second = segments[position - 1], segments[position]
        if first.toIndex != second.fromIndex:
            continue  # the two segments are separated by a gap: no continuous course to compare
        delta = _signed_angle_delta(first.bearingDeg, second.bearingDeg)
        absolute = abs(delta)
        total_change += absolute
        max_change = max(max_change, absolute)
        junction = points[second.fromIndex]
        if absolute < config.course_change_threshold_deg:
            continue
        if not _both_at_least(first.impliedSpeedKn, second.impliedSpeedKn,
                              config.min_speed_for_course_change_kn):
            continue  # too slow (or unknown) for the turn to be meaningful: COG jitters at rest
        events.append(CourseChangeEvent(
            index=junction.index, timestamp=junction.timestamp,
            latitude=junction.latitude, longitude=junction.longitude,
            fromBearingDeg=first.bearingDeg, toBearingDeg=second.bearingDeg,
            changeDeg=delta, absoluteChangeDeg=absolute,
            speedKn=junction.sogKn, sourceLine=junction.sourceLine,
        ))
    return events, total_change, max_change


# ---------------------------------------------------------------------------
# One vessel
# ---------------------------------------------------------------------------
def build_trajectory(
    mmsi: str,
    records: Sequence[Mapping[str, Any]],
    config: Optional[TrajectoryConfig] = None,
    *,
    extract_start_epoch: Optional[int] = None,
    extract_end_epoch: Optional[int] = None,
) -> VesselTrajectory:
    """Build one vessel's trajectory from its cleaned records."""
    config = config or TrajectoryConfig()
    ordered = sorted(records, key=lambda record: (record["epochSeconds"], record["sourceLine"]))
    points = [
        TrajectoryPoint(
            index=index, timestamp=record["timestamp"] or "", epochSeconds=record["epochSeconds"],
            latitude=record["latitude"], longitude=record["longitude"], sogKn=record["sogKn"],
            cogDeg=record["cogDeg"], headingDeg=record["headingDeg"],
            navigationStatus=record["navigationStatus"], sourceLine=record["sourceLine"],
            warnings=list(record.get("warnings") or []),
        )
        for index, record in enumerate(ordered)
    ]
    reference = ordered[0]
    segments: List[TrajectorySegment] = []
    gaps: List[TrajectoryGap] = []
    legs: List[List[int]] = [[0]] if points else []
    same_timestamp_pairs = 0

    for index in range(1, len(points)):
        previous, current = points[index - 1], points[index]
        elapsed = float(current.epochSeconds - previous.epochSeconds)
        distance = haversine_km(previous.latitude, previous.longitude, current.latitude, current.longitude)
        if elapsed > config.gap_threshold_seconds:
            implied = implied_speed_kn(distance, elapsed)
            gaps.append(TrajectoryGap(
                startTimestamp=previous.timestamp, endTimestamp=current.timestamp,
                durationSeconds=elapsed,
                lastPosition=_position_dict(previous), nextPosition=_position_dict(current),
                straightLineKm=distance, impliedSpeedKn=implied,
                initialBearingDeg=initial_bearing_deg(previous.latitude, previous.longitude,
                                                      current.latitude, current.longitude),
                impliedSpeedExceedsConfiguredMaximum=(
                    implied is not None and implied > config.max_plausible_speed_kn),
            ))
            legs.append([index])
        elif elapsed > 0.0:
            segments.append(TrajectorySegment(
                fromIndex=index - 1, toIndex=index,
                startTimestamp=previous.timestamp, endTimestamp=current.timestamp,
                elapsedSeconds=elapsed, distanceKm=distance,
                impliedSpeedKn=implied_speed_kn(distance, elapsed),
                bearingDeg=initial_bearing_deg(previous.latitude, previous.longitude,
                                               current.latitude, current.longitude),
                reportedSogKn=(previous.sogKn if previous.sogKn is not None else current.sogKn),
            ))
            legs[-1].append(index)
        else:
            same_timestamp_pairs += 1
            legs[-1].append(index)

    observed_distance = sum(segment.distanceKm for segment in segments)
    straight_line_gap = sum(gap.straightLineKm for gap in gaps)
    duration_seconds = float(points[-1].epochSeconds - points[0].epochSeconds) if len(points) > 1 else 0.0

    moving_seconds = slow_seconds = stopped_seconds = 0.0
    for segment in segments:
        speed = segment.impliedSpeedKn if segment.impliedSpeedKn is not None else segment.reportedSogKn
        if speed is None:
            continue
        if speed < config.stop_speed_kn:
            stopped_seconds += segment.elapsedSeconds
        elif speed < config.slow_speed_kn:
            slow_seconds += segment.elapsedSeconds
        else:
            moving_seconds += segment.elapsedSeconds

    reported_speeds = [point.sogKn for point in points if point.sogKn is not None]
    periods = _detect_stop_slow_periods(points, legs, config)
    course_changes, total_course_change, max_course_change = _detect_course_changes(points, segments, config)

    line = [[round(point.longitude, 6), round(point.latitude, 6)] for point in points]
    geometry = {"type": "LineString", "coordinates": line} if len(line) >= 2 else None
    geometry_by_leg: List[Dict[str, Any]] = []
    for leg in legs:
        if len(leg) >= 2:
            geometry_by_leg.append({
                "type": "LineString",
                "coordinates": [[round(points[i].longitude, 6), round(points[i].latitude, 6)] for i in leg],
                "startIndex": leg[0], "endIndex": leg[-1],
            })

    lat_values = [point.latitude for point in points]
    lon_values = [point.longitude for point in points]
    warnings: List[str] = []
    unobserved_before = (float(points[0].epochSeconds - extract_start_epoch)
                         if points and extract_start_epoch is not None else None)
    unobserved_after = (float(extract_end_epoch - points[-1].epochSeconds)
                        if points and extract_end_epoch is not None else None)

    missing_speed = sum(1 for point in points if point.sogKn is None)
    starts_at_boundary = (unobserved_before is not None
                          and unobserved_before <= config.gap_threshold_seconds)
    ends_at_boundary = (unobserved_after is not None
                        and unobserved_after <= config.gap_threshold_seconds)

    if len(points) == 1:
        warnings.append("only one record: no segments, no movement metrics and no gaps can be derived")
    if same_timestamp_pairs:
        warnings.append(
            f"{same_timestamp_pairs} pair(s) of records share a timestamp; no speed can be "
            "inferred from them, so they do not form a segment"
        )
    if missing_speed:
        warnings.append(
            f"{missing_speed} record(s) have no speed over ground (the value was removed during "
            "cleaning); they are excluded from speed statistics but their positions are still used"
        )
    if gaps:
        total_gap_hours = sum(gap.durationSeconds for gap in gaps) / 3600.0
        warnings.append(
            f"{len(gaps)} structural gap(s) totalling {total_gap_hours:.2f} h; whether a gap is "
            "relevant is assessed in the AIS gap analysis phase, and a gap alone implies nothing"
        )
    if unobserved_before is not None and not starts_at_boundary:
        warnings.append(
            f"history begins {unobserved_before / 3600.0:.2f} h after the start of the extract; "
            "the absence of records before the first record is unbounded and cannot be measured"
        )
    if unobserved_after is not None and not ends_at_boundary:
        warnings.append(
            f"history ends {unobserved_after / 3600.0:.2f} h before the end of the extract; "
            "the absence of records after the last record is unbounded and cannot be measured"
        )

    stats: Dict[str, Any] = {
        "recordCount": len(points),
        "segmentCount": len(segments),
        "legCount": len(legs),
        "gapCount": len(gaps),
        "stopPeriodCount": sum(1 for period in periods if period.kind == "stop"),
        "slowPeriodCount": sum(1 for period in periods if period.kind == "slow"),
        "courseChangeCount": len(course_changes),
        "firstTimestamp": points[0].timestamp if points else None,
        "lastTimestamp": points[-1].timestamp if points else None,
        "durationSeconds": round(duration_seconds, 3),
        "durationHours": round(duration_seconds / 3600.0, 4),
        "observedDistanceKm": round(observed_distance, 6),
        "straightLineGapKm": round(straight_line_gap, 6),
        "gapSeconds": round(sum(gap.durationSeconds for gap in gaps), 3),
        "longestGapSeconds": round(max((gap.durationSeconds for gap in gaps), default=0.0), 3),
        "averageSpeedKn": (round(observed_distance / (duration_seconds / 3600.0) / KNOTS_TO_KMH, 3)
                           if duration_seconds > 0 else None),
        "averageSpeedWhileMovingKn": (
            round(observed_distance / ((moving_seconds + slow_seconds) / 3600.0) / KNOTS_TO_KMH, 3)
            if (moving_seconds + slow_seconds) > 0 else None),
        "maxReportedSogKn": round(max(reported_speeds), 3) if reported_speeds else None,
        "minReportedSogKn": round(min(reported_speeds), 3) if reported_speeds else None,
        "meanReportedSogKn": (round(sum(reported_speeds) / len(reported_speeds), 3)
                              if reported_speeds else None),
        "medianReportedSogKn": (round(_median(reported_speeds), 3) if reported_speeds else None),
        "recordsWithMissingSpeed": missing_speed,
        "movingSeconds": round(moving_seconds, 3),
        "slowSeconds": round(slow_seconds, 3),
        "stoppedSeconds": round(stopped_seconds, 3),
        "totalAbsoluteCourseChangeDeg": round(total_course_change, 3),
        "maxCourseChangeDeg": round(max_course_change, 3),
        "sameTimestampPairs": same_timestamp_pairs,
        "firstPosition": _position_dict(points[0]) if points else None,
        "lastPosition": _position_dict(points[-1]) if points else None,
        "bounds": ({"minLat": round(min(lat_values), 6), "maxLat": round(max(lat_values), 6),
                    "minLon": round(min(lon_values), 6), "maxLon": round(max(lon_values), 6)}
                   if points else None),
        "unobservedBeforeStartSeconds": (round(unobserved_before, 3)
                                         if unobserved_before is not None else None),
        "unobservedAfterEndSeconds": (round(unobserved_after, 3)
                                      if unobserved_after is not None else None),
        "startsAtExtractBoundary": starts_at_boundary,
        "endsAtExtractBoundary": ends_at_boundary,
        "distanceDefinition": "sum of great-circle distances within contiguous runs; gap crossings excluded",
    }
    return VesselTrajectory(
        mmsi=mmsi,
        imo=(str(reference["imo"]).strip() if reference.get("imo") else None),
        vesselName=(str(reference["vesselName"]).strip() if reference.get("vesselName") else None),
        vesselType=(int(reference["vesselType"]) if reference.get("vesselType") is not None else None),
        datasetLabel=(str(reference["datasetLabel"]).strip() if reference.get("datasetLabel") else None),
        synthetic=bool(reference.get("synthetic")),
        points=points, segments=segments, gaps=gaps, stopSlowPeriods=periods,
        courseChanges=course_changes, geometry=geometry, geometryByLeg=geometry_by_leg,
        stats=stats, warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Fleet level
# ---------------------------------------------------------------------------
def build_trajectories(
    records: Sequence[Mapping[str, Any]],
    config: Optional[TrajectoryConfig] = None,
    *,
    source: Optional[Dict[str, Any]] = None,
    extract_start_epoch: Optional[int] = None,
    extract_end_epoch: Optional[int] = None,
) -> TrajectoryCollection:
    """Build one trajectory per vessel and fleet-level statistics."""
    config = config or TrajectoryConfig()
    source = dict(source or {})
    grouped, skipped = _normalise_records(records)
    if not grouped:
        return TrajectoryCollection(
            trajectories=[], statistics={"counts": {"vessels": 0, "records": 0}},
            source=source, config=config.describe(), skippedRecords=skipped,
            warnings=["no usable records were supplied: there is nothing to reconstruct"],
            notes=_collection_notes(config),
        )

    all_epochs = [record["epochSeconds"] for group in grouped.values() for record in group]
    if extract_start_epoch is None:
        extract_start_epoch = min(all_epochs)
    if extract_end_epoch is None:
        extract_end_epoch = max(all_epochs)

    trajectories = [
        build_trajectory(mmsi, grouped[mmsi], config,
                         extract_start_epoch=extract_start_epoch, extract_end_epoch=extract_end_epoch)
        for mmsi in sorted(grouped)
    ]

    counts = {
        "vessels": len(trajectories),
        "records": sum(trajectory.record_count for trajectory in trajectories),
        "segments": sum(len(trajectory.segments) for trajectory in trajectories),
        "gaps": sum(len(trajectory.gaps) for trajectory in trajectories),
        "stopPeriods": sum(trajectory.stats["stopPeriodCount"] for trajectory in trajectories),
        "slowPeriods": sum(trajectory.stats["slowPeriodCount"] for trajectory in trajectories),
        "courseChanges": sum(len(trajectory.courseChanges) for trajectory in trajectories),
        "vesselsWithGaps": sum(1 for trajectory in trajectories if trajectory.gaps),
        "vesselsWithStopPeriods": sum(1 for trajectory in trajectories if trajectory.stopSlowPeriods),
        "vesselsWithCourseChanges": sum(1 for trajectory in trajectories if trajectory.courseChanges),
        "recordsWithMissingSpeed": sum(trajectory.stats["recordsWithMissingSpeed"]
                                       for trajectory in trajectories),
        "skippedRecords": len(skipped),
        "syntheticRecords": sum(1 for trajectory in trajectories if trajectory.synthetic),
    }
    totals = {
        "observedDistanceKm": round(sum(trajectory.stats["observedDistanceKm"]
                                        for trajectory in trajectories), 3),
        "straightLineGapKm": round(sum(trajectory.stats["straightLineGapKm"]
                                       for trajectory in trajectories), 3),
        "gapHours": round(sum(trajectory.stats["gapSeconds"] for trajectory in trajectories) / 3600.0, 4),
        "movingHours": round(sum(trajectory.stats["movingSeconds"] for trajectory in trajectories) / 3600.0, 4),
        "stoppedHours": round(sum(trajectory.stats["stoppedSeconds"] for trajectory in trajectories) / 3600.0, 4),
        "gapThresholdSeconds": config.gap_threshold_seconds,
    }

    def highlight(key: str, value_of, haystack, reverse: bool = True) -> Optional[Dict[str, Any]]:
        items = [(value_of(trajectory), trajectory.mmsi) for trajectory in haystack]
        items = [(value, mmsi) for value, mmsi in items if value is not None]
        if not items:
            return None
        value, mmsi = (max(items) if reverse else min(items))
        return {"mmsi": mmsi, key: round(float(value), 3)}

    highlights = {
        "longestGap": highlight("durationHours",
                                lambda t: (t.stats["longestGapSeconds"] / 3600.0) if t.gaps else None,
                                trajectories),
        "fastestReportedSpeed": highlight("sogKn", lambda t: t.stats["maxReportedSogKn"], trajectories),
        "mostCourseChanges": highlight("count", lambda t: float(len(t.courseChanges)), trajectories),
        "lowestMedianSpeed": highlight("sogKn", lambda t: t.stats["medianReportedSogKn"], trajectories, reverse=False),
    }
    statistics = {"counts": counts, "totals": totals, "highlights": highlights,
                  "extractWindow": {"startEpochSeconds": int(extract_start_epoch),
                                    "endEpochSeconds": int(extract_end_epoch)}}
    return TrajectoryCollection(
        trajectories=trajectories, statistics=statistics, source=source,
        config=config.describe(), skippedRecords=skipped,
        warnings=_collection_warnings(source, counts, trajectories),
        notes=_collection_notes(config),
    )


def build_trajectories_from_cleaning(
    result: CleaningResult,
    config: Optional[TrajectoryConfig] = None,
) -> TrajectoryCollection:
    """Convenience: build trajectories straight from a Phase 3 CleaningResult."""
    time_range = (result.statistics or {}).get("timeRange", {})
    return build_trajectories(
        result.records, config,
        source=dict(result.source or {}),
        extract_start_epoch=_epoch_from_timestamp(time_range.get("start")),
        extract_end_epoch=_epoch_from_timestamp(time_range.get("end")),
    )


def trajectory_from_records(
    records: Sequence[Mapping[str, Any]], config: Optional[TrajectoryConfig] = None,
) -> TrajectoryCollection:
    """Alias kept explicit so callers can build from a plain record list."""
    return build_trajectories(records, config)


def _collection_warnings(
    source: Dict[str, Any], counts: Dict[str, Any], trajectories: Sequence[VesselTrajectory],
) -> List[str]:
    warnings: List[str] = []
    if source.get("synthetic") or counts.get("syntheticRecords"):
        warnings.append("AIS: Synthetic Demonstration Dataset - synthetic tracks are demonstration "
                        "data and are never presented as real-world evidence")
    if counts.get("skippedRecords"):
        warnings.append(f"{counts['skippedRecords']} record(s) could not be used and are listed under "
                        "skippedRecords with reasons - nothing was dropped silently")
    if counts.get("vesselsWithGaps"):
        warnings.append(f"{counts['gaps']} structural gap(s) across {counts['vesselsWithGaps']} vessel(s); "
                        "gap relevance is assessed in the AIS gap analysis phase")
    if counts.get("vessels") and any(not trajectory.stats["startsAtExtractBoundary"]
                                     for trajectory in trajectories):
        warnings.append("some vessels have partial history inside the extract; absence of records "
                        "before the first or after the last record is unbounded and is not a gap")
    if counts.get("recordsWithMissingSpeed"):
        warnings.append(f"{counts['recordsWithMissingSpeed']} record(s) carry no speed over ground")
    return warnings


def _collection_notes(config: TrajectoryConfig) -> List[str]:
    return [
        "Distances are great-circle distances summed over contiguous runs of records; the straight "
        "line across a gap is reported separately and is NOT counted as observed travel.",
        "A gap here is a STRUCTURAL fact (an interval with no records). Whether it is compatible "
        "with a reconstructed origin region and release window is decided in the AIS gap analysis "
        "phase, and a gap alone never implies suspicion.",
        "Stop and slow periods are DESCRIPTIVE. Legitimate traffic produces them (waiting, fishing, "
        "harbour work); comparison against a vessel's own behavioural baseline is a later phase.",
        f"Thresholds are configurable PROTOTYPE values (gap {config.gap_threshold_seconds:.0f} s, "
        f"stop < {config.stop_speed_kn} kn, slow < {config.slow_speed_kn} kn, "
        f"course change >= {config.course_change_threshold_deg} deg); they are not scientific constants.",
        "geometryByLeg splits the track wherever a gap occurs, so a map never draws a straight line "
        "through a period for which no positions were recorded.",
        "Nothing in this output concludes anything about a vessel.",
    ]


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def print_trajectory_summary(collection: TrajectoryCollection) -> None:
    counts = collection.statistics.get("counts", {})
    totals = collection.statistics.get("totals", {})
    line = "=" * 124
    print(line)
    print("ABYSS - AIS trajectory construction report (Phase 4)")
    print(f"  provider      : {collection.source.get('provider', 'unknown')}")
    print(f"  synthetic     : {collection.synthetic}")
    print(f"  module        : ais.trajectory {MODULE_VERSION}")
    config = collection.config
    print(f"  thresholds    : gap >= {config['gapThresholdSeconds']:.0f} s, stop < {config['stopSpeedKn']} kn, "
          f"slow < {config['slowSpeedKn']} kn, turn >= {config['courseChangeThresholdDeg']} deg")
    print(line)
    print("COUNTS")
    for key in ("vessels", "records", "segments", "gaps", "vesselsWithGaps", "stopPeriods", "slowPeriods",
                "courseChanges", "recordsWithMissingSpeed", "skippedRecords"):
        print(f"  {key:<26} : {counts.get(key)}")
    print()
    print("TOTALS")
    print(f"  observed distance (km)     : {totals.get('observedDistanceKm')}")
    print(f"  straight line across gaps  : {totals.get('straightLineGapKm')} km (not counted as travel)")
    print(f"  time with movement (h)     : {totals.get('movingHours')}")
    print(f"  time stopped (h)           : {totals.get('stoppedHours')}")
    print(f"  total gap time (h)         : {totals.get('gapHours')}")
    highlights = collection.statistics.get("highlights", {})
    for key, value in highlights.items():
        print(f"  {key:<26} : {value}")
    print()
    header = (f"  {'MMSI':<10}{'VESSEL':<22}{'RECS':>6}{'HOURS':>8}{'KM':>10}{'AVG_KN':>8}"
              f"{'MAX_KN':>8}{'STOPS':>7}{'SLOW':>6}{'GAPS':>6}{'GAP_H':>8}{'TURNS':>7}")
    print(header)
    print("  " + "-" * 120)

    def number(value: Any, width: int, decimals: int = 1) -> str:
        return "-".rjust(width) if value is None else f"{value:.{decimals}f}".rjust(width)

    for trajectory in collection.trajectories:
        stats = trajectory.stats
        name = (trajectory.vesselName or "(unnamed)")[:20]
        print(f"  {trajectory.mmsi:<10}{name:<22}{stats['recordCount']:>6}"
              f"{number(stats['durationHours'], 8)}{number(stats['observedDistanceKm'], 10)}"
              f"{number(stats['averageSpeedKn'], 8)}{number(stats['maxReportedSogKn'], 8)}"
              f"{stats['stopPeriodCount']:>7}{stats['slowPeriodCount']:>6}{stats['gapCount']:>6}"
              f"{number(stats['gapSeconds'] / 3600.0, 8, 2)}{len(trajectory.courseChanges):>7}")
    print("  " + "-" * 120)
    print("  RECS = accepted positions, HOURS = observed span, KM = observed travel within contiguous runs,")
    print("  AVG_KN = KM / observed span, MAX_KN = highest reported speed over ground,")
    print("  STOPS/SLOW = descriptive low-speed periods, GAPS = structural gaps, TURNS = course changes >= threshold")
    print()
    print("STRUCTURAL GAPS (facts only: relevance is assessed in the AIS gap analysis phase)")
    any_gap = False
    for trajectory in collection.trajectories:
        for gap in trajectory.gaps:
            any_gap = True
            flag = "EXCEEDS-CONFIGURED-MAX" if gap.impliedSpeedExceedsConfiguredMaximum else "within-configured-max"
            implied = "unknown" if gap.impliedSpeedKn is None else f"{gap.impliedSpeedKn:.1f} kn"
            print(f"  {trajectory.mmsi}  {gap.startTimestamp} -> {gap.endTimestamp}  "
                  f"{gap.durationSeconds / 3600.0:5.2f} h  straight {gap.straightLineKm:7.1f} km  "
                  f"implied {implied:>10}  {flag}")
    if not any_gap:
        print("  (none)")
    print()
    print("FLEET WARNINGS")
    for warning in collection.warnings:
        print(f"  - {warning}")
    print()
    print("METHOD NOTES")
    for note in collection.notes:
        print(f"  - {note}")
    print(line)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build AIS vessel trajectories (Phase 4) from the cleaned CASE-001 extract.",
    )
    parser.add_argument("--input", default=None,
                        help="raw AIS CSV to clean and build trajectories from "
                             "(default: the synthetic CASE-001 demo extract)")
    parser.add_argument("--json", dest="json_out", default=None,
                        help="write the full trajectory collection as JSON")
    parser.add_argument("--gap-threshold-minutes", dest="gap_minutes", type=float, default=None,
                        help="interval with no records treated as a structural gap (default 30)")
    parser.add_argument("--course-change-threshold-deg", dest="turn_deg", type=float, default=None,
                        help="course change considered significant (default 30)")
    parser.add_argument("--stop-speed-kn", dest="stop_kn", type=float, default=None,
                        help="speed below which a vessel counts as stopped (default 0.5)")
    parser.add_argument("--slow-speed-kn", dest="slow_kn", type=float, default=None,
                        help="speed below which a vessel counts as slow (default 3.0)")
    parser.add_argument("--quiet", action="store_true", help="suppress the printed summary")
    args = parser.parse_args(argv)

    defaults = TrajectoryConfig()
    config = TrajectoryConfig(
        gap_threshold_seconds=(args.gap_minutes * 60.0 if args.gap_minutes is not None
                               else defaults.gap_threshold_seconds),
        stop_speed_kn=(args.stop_kn if args.stop_kn is not None else defaults.stop_speed_kn),
        slow_speed_kn=(args.slow_kn if args.slow_kn is not None else defaults.slow_speed_kn),
        min_period_seconds=defaults.min_period_seconds,
        min_period_records=defaults.min_period_records,
        course_change_threshold_deg=(args.turn_deg if args.turn_deg is not None
                                     else defaults.course_change_threshold_deg),
        min_speed_for_course_change_kn=defaults.min_speed_for_course_change_kn,
        max_plausible_speed_kn=defaults.max_plausible_speed_kn,
    )

    cleaning_result = clean_csv(Path(args.input)) if args.input else clean_demo_case()
    collection = build_trajectories_from_cleaning(cleaning_result, config)

    if args.json_out:
        payload = collection.to_dict()
        payload["cleaningSummary"] = {
            "rowsIn": cleaning_result.statistics["counts"]["rowsIn"],
            "records": cleaning_result.statistics["counts"]["records"],
            "rowsRejected": cleaning_result.statistics["counts"]["rowsRejected"],
            "warnings": cleaning_result.warnings,
        }
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")

    if args.quiet:
        counts = collection.statistics["counts"]
        print(f"built {counts['vessels']} trajectories from {counts['records']} records: "
              f"{counts['segments']} segments, {counts['gaps']} gaps, {counts['stopPeriods']} stop and "
              f"{counts['slowPeriods']} slow periods, {counts['courseChanges']} significant course changes")
    else:
        print_trajectory_summary(collection)
    return 0


if __name__ == "__main__":
    sys.exit(main())
