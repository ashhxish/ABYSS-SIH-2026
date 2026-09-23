"""ABYSS - behavioural baseline and anomaly analysis (Phase 8).

PURPOSE
    Compare each vessel with ITSELF: does its behaviour during the release
    window depart from its own track-wide pattern? Output is a raw anomaly
    magnitude (0-1) plus named components. The SUSPICION SCORING phase decides
    whether the anomaly counts - it only does so when the vessel was also
    spatially present in the origin region during the window, so a wild
    manoeuvre 200 km away is context, never evidence.

WHY THIS HYBRID (own-baseline + absolute references)
    docs/methodology.md: high speed, turns and stops are legitimate for many
    vessels. A tug stopping in harbour is normal FOR A TUG; the same stop on a
    transit tanker is not. Median speed and slow fraction are therefore compared
    window-vs-own-baseline (speedShift, loiterExcess). But a vessel that is
    erratic across its WHOLE track differs from itself nowhere, so a pure
    baseline comparison would never see it (scenario case F: strong speed
    swings and course changes far from the region). Speed spread and turn rate
    are therefore measured on the EVENT WINDOW against documented absolute
    references - both views are reported as separate components.

WHAT IT IS NOT
    No cross-vessel comparison, no scoring, no conclusion that anyone did
    anything wrong. "Anomaly" means "differs from its own baseline", nothing
    more; scoring and gating belong to the evidence engine.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):  # executed directly as a script
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.ais.trajectory import VesselTrajectory
    from app.timeutils import ReleaseWindow, epoch_seconds
else:
    from app.ais.trajectory import VesselTrajectory
    from app.timeutils import ReleaseWindow, epoch_seconds

__all__ = ["BehaviourConfig", "BehaviourAssessment", "assess_behaviour"]


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _median(values: List[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


@dataclass(frozen=True)
class BehaviourConfig:
    """Thresholds for raw anomaly detection. Prototype values, all reported."""

    report_threshold: float = 0.30          # raw >= this is reported as an anomaly
    variability_reference_kn: float = 6.0   # WINDOW speed spread considered notable
    turn_reference_per_hour: float = 1.0    # WINDOW course changes/hour considered notable
    slow_speed_kn: float = 3.0              # aligns with TrajectoryConfig.slow_speed_kn
    min_window_records: int = 3             # fewer -> no event statistics

    def __post_init__(self) -> None:
        if not (0.0 <= self.report_threshold <= 1.0):
            raise ValueError(f"report_threshold must be in [0, 1], got {self.report_threshold}")
        if self.variability_reference_kn <= 0:
            raise ValueError("variability_reference_kn must be > 0")
        if self.turn_reference_per_hour <= 0:
            raise ValueError("turn_reference_per_hour must be > 0")
        if self.slow_speed_kn < 0:
            raise ValueError("slow_speed_kn must be >= 0")
        if self.min_window_records < 1:
            raise ValueError("min_window_records must be >= 1")

    def describe(self) -> Dict[str, Any]:
        return {
            "reportThreshold": self.report_threshold,
            "variabilityReferenceKn": self.variability_reference_kn,
            "turnReferencePerHour": self.turn_reference_per_hour,
            "slowSpeedKn": self.slow_speed_kn,
            "minWindowRecords": self.min_window_records,
        }


@dataclass
class BehaviourAssessment:
    """Raw anomaly vs the vessel's own baseline, with and without the gate."""

    mmsi: str
    baseline: Dict[str, Any] = dataclass_field(default_factory=dict)
    window: Dict[str, Any] = dataclass_field(default_factory=dict)
    components: Dict[str, float] = dataclass_field(default_factory=dict)
    raw_anomaly: float = 0.0
    is_anomaly: bool = False
    scored_eligible: bool = False
    scored_anomaly: float = 0.0
    description: str = "insufficient data"
    notes: List[str] = dataclass_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mmsi": self.mmsi,
            "baseline": dict(self.baseline),
            "window": dict(self.window),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "rawAnomaly": round(self.raw_anomaly, 4),
            "isAnomaly": self.is_anomaly,
            "scoredEligible": self.scored_eligible,
            "scoredAnomaly": round(self.scored_anomaly, 4),
            "description": self.description,
            "notes": list(self.notes),
            "note": ("raw anomaly compares the vessel with itself; the scoring phase "
                     "gates it on spatial presence in the origin region"),
        }


# Prototype component weights of the raw anomaly. Reported verbatim in every
# assessment's notes; change them here, not silently in a caller.
COMPONENT_WEIGHTS = {
    "speedShift": 0.30,
    "variability": 0.30,
    "turnExcess": 0.20,
    "loiterExcess": 0.20,
}


def assess_behaviour(
    trajectory: VesselTrajectory,
    window: ReleaseWindow,
    in_region_during_window: bool,
    config: Optional[BehaviourConfig] = None,
) -> BehaviourAssessment:
    """Raw own-baseline anomaly for the release window.

    `in_region_during_window` is the spatial gate from Phase 5: when False the
    anomaly is still computed and REPORTED, but `scored_anomaly` is 0 - the
    evidence engine only ever scores behaviour on vessels that were present in
    the origin region during the window.
    """
    cfg = config or BehaviourConfig()
    assessment = BehaviourAssessment(
        mmsi=trajectory.mmsi, scored_eligible=bool(in_region_during_window))

    all_speeds = [p.sogKn for p in trajectory.points if p.sogKn is not None]
    window_points = [p for p in trajectory.points if window.contains(p.epochSeconds)]
    window_speeds = [p.sogKn for p in window_points if p.sogKn is not None]
    if not all_speeds or len(window_speeds) < cfg.min_window_records:
        assessment.notes.append(
            "insufficient speed observations in the release window for a baseline "
            "comparison; raw anomaly left at 0"
        )
        return assessment

    first, last = trajectory.points[0], trajectory.points[-1]
    track_hours = max((last.epochSeconds - first.epochSeconds) / 3600.0, 0.0)
    base_median = _median(all_speeds)
    base_spread = max(all_speeds) - min(all_speeds)
    base_slow = sum(1 for s in all_speeds if s <= cfg.slow_speed_kn) / len(all_speeds)
    base_turns = len(trajectory.courseChanges) / track_hours if track_hours > 0 else 0.0

    win_median = _median(window_speeds)
    win_spread = max(window_speeds) - min(window_speeds)
    win_slow = sum(1 for s in window_speeds if s <= cfg.slow_speed_kn) / len(window_speeds)
    win_turns = sum(1 for ev in trajectory.courseChanges
                    if window.contains(epoch_seconds(ev.timestamp)))
    win_turns_per_hour = win_turns / window.duration_hours()

    speed_shift = _clamp(abs(win_median - base_median) / max(base_median, 1.0))
    # Variability and turn rate are measured on the EVENT WINDOW against absolute
    # references, not against the track baseline: a vessel that is erratic across
    # its whole track differs from itself nowhere, so a baseline comparison alone
    # would never see it (scenario case F). Median speed and slow fraction stay
    # own-baseline comparisons (speed_shift, loiter_excess) so normal working
    # patterns are not flagged by absolute speed alone.
    variability = _clamp(win_spread / cfg.variability_reference_kn)
    turn_excess = _clamp(win_turns_per_hour / cfg.turn_reference_per_hour)
    loiter_excess = _clamp(win_slow - base_slow)
    raw = _clamp(COMPONENT_WEIGHTS["speedShift"] * speed_shift
                 + COMPONENT_WEIGHTS["variability"] * variability
                 + COMPONENT_WEIGHTS["turnExcess"] * turn_excess
                 + COMPONENT_WEIGHTS["loiterExcess"] * loiter_excess)

    phrases: List[str] = []
    if speed_shift >= 0.3:
        phrases.append("slowdown against own baseline" if win_median < base_median
                       else "speed lift against own baseline")
    if variability >= 0.5:
        phrases.append("erratic speeds during the window")
    if turn_excess >= 0.5:
        phrases.append("frequent course changes during the window")
    if loiter_excess >= 0.2:
        phrases.append("extended slow/loitering periods during the window")
    description = "; ".join(phrases) if phrases else "broadly consistent with own baseline"

    is_anomaly = raw >= cfg.report_threshold
    notes = []
    if is_anomaly and not in_region_during_window:
        notes.append("behaviour anomaly detected but the vessel was outside the origin "
                     "region during the window - reported as context, scored 0")
    elif not is_anomaly:
        notes.append("behaviour consistent with own baseline during the window")
    notes.append(
        "raw = 0.30*speedShift(window median vs own baseline) + 0.30*variability("
        "window speed spread vs reference) + 0.20*turnExcess(window rate vs "
        "reference) + 0.20*loiterExcess(window slow fraction vs own baseline); "
        "prototype component weights"
    )

    assessment.baseline = {
        "records": len(all_speeds),
        "medianSogKn": round(base_median, 3),
        "spreadSogKn": round(base_spread, 3),
        "turnsPerHour": round(base_turns, 3),
        "slowFraction": round(base_slow, 4),
        "trackHours": round(track_hours, 3),
    }
    assessment.window = {
        "records": len(window_speeds),
        "medianSogKn": round(win_median, 3),
        "spreadSogKn": round(win_spread, 3),
        "turnsPerHour": round(win_turns_per_hour, 3),
        "slowFraction": round(win_slow, 4),
        "hours": round(window.duration_hours(), 3),
    }
    assessment.components = {"speedShift": speed_shift, "variability": variability,
                             "turnExcess": turn_excess, "loiterExcess": loiter_excess}
    assessment.raw_anomaly = raw
    assessment.is_anomaly = is_anomaly
    assessment.scored_eligible = bool(in_region_during_window)
    assessment.scored_anomaly = raw if in_region_during_window else 0.0
    assessment.description = description
    assessment.notes = notes
    return assessment