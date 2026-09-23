"""ABYSS - evidence scoring engine (Phase 10).

PURPOSE
    Turn measured facts (compatibility, behaviour, gaps) into an EXPLAINABLE
    suspicion score in [0, 100]: one named factor per evidence source, points
    from that factor's weight, and a human-readable reason for EVERY factor -
    including the factors that contributed zero. Ordering lives in ranking.py.

DEFAULT WEIGHTS (docs/methodology.md section 7; configurable, validated, reported)

    35  spatial     distance to origin region
                    proximity of the closest in-window approach to the region,
                    decaying linearly to zero at the configured falloff distance
    25  temporal    proximity to release window
                    present inside the origin region while the window was open
    20  trajectory  course-change correlation
                    plausible observed motion transiting the region during the
                    window (an uncorrelated track has nothing to correlate)
    10  behaviour   stop/slow pattern
                    own-baseline anomaly during the window, GATED to zero
                    unless the vessel was present inside the region
    10  gap         AIS-gap behaviour
                    feasibility x relevance of gaps, CAPPED at 0.30 of this
                    factor: a gap is the LIGHTEST factor because it is the most
                    ambiguous, so even a perfect gap can add 3 points of 100

GOLDEN RULES ENFORCED HERE
    * a gap alone never raises suspicion (cap above; relevance requires region
      proximity anyway) and the ABSENCE of a gap never helps or hurts;
    * behavioural anomalies outside the region are reported but score 0;
    * zero points means "no evidence of this kind", and the reason says why.

WHAT IT IS NOT
    No probability, no verdict - an evidence summary for investigation support.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):  # executed directly as a script
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.ais.filtering import CompatibilityAssessment
    from app.ais.gap_analysis import GapAssessment
    from app.behaviour.baseline import BehaviourAssessment
    from app.timeutils import ReleaseWindow
else:
    from app.ais.filtering import CompatibilityAssessment
    from app.ais.gap_analysis import GapAssessment
    from app.behaviour.baseline import BehaviourAssessment
    from app.timeutils import ReleaseWindow

__all__ = ["EvidenceWeights", "ScoringConfig", "CandidateEvidence",
           "ScoredCandidate", "score_candidate"]

FACTOR_KEYS = ("spatial", "gap", "trajectory", "behaviour", "temporal")
FACTOR_TITLES = {
    "spatial": "distance to origin region",
    "gap": "AIS-gap behaviour",
    "trajectory": "course-change correlation",
    "behaviour": "stop/slow pattern",
    "temporal": "proximity to release window",
}


@dataclass(frozen=True)
class EvidenceWeights:
    """Configurable factor weights (points at full evidence). Defaults sum to 100.

    The defaults follow docs/methodology.md section 7 exactly. A gap is deliberately
    the lightest factor: it is the most ambiguous evidence in the chain, so a perfect
    gap is worth 3 points of 100 (10 points capped at 30 %).
    """

    spatial: float = 35.0
    gap: float = 10.0
    trajectory: float = 20.0
    behaviour: float = 10.0
    temporal: float = 25.0

    def __post_init__(self) -> None:
        for key in FACTOR_KEYS:
            value = getattr(self, key)
            if value < 0:
                raise ValueError(f"weight '{key}' must be >= 0, got {value}")
        if self.total <= 0:
            raise ValueError(f"weights must sum to a positive value, got {self.total}")

    @property
    def total(self) -> float:
        return float(self.spatial + self.gap + self.trajectory + self.behaviour + self.temporal)

    def get(self, key: str) -> float:
        if key not in FACTOR_KEYS:
            raise KeyError(f"unknown evidence factor {key!r}")
        return float(getattr(self, key))

    def describe(self) -> Dict[str, float]:
        return {key: self.get(key) for key in FACTOR_KEYS}


@dataclass(frozen=True)
class ScoringConfig:
    """Thresholds owned by the engine. Prototype values, all reported."""

    spatial_falloff_km: float = 30.0   # keep in sync with CompatibilityConfig
    gap_relevance_cap: float = 0.30    # max share of the gap factor per gap

    def __post_init__(self) -> None:
        if self.spatial_falloff_km <= 0:
            raise ValueError("spatial_falloff_km must be > 0")
        if not (0.0 <= self.gap_relevance_cap <= 1.0):
            raise ValueError("gap_relevance_cap must be in [0, 1]")

    def describe(self) -> Dict[str, Any]:
        return {"spatialFalloffKm": self.spatial_falloff_km,
                "gapRelevanceCap": self.gap_relevance_cap}


@dataclass
class CandidateEvidence:
    """Everything the engine needs for one vessel - already measured elsewhere."""

    mmsi: str
    vessel_id: Optional[str]
    name: str
    vessel_type: str
    compatibility: CompatibilityAssessment
    behaviour: BehaviourAssessment
    gaps: GapAssessment
    window: ReleaseWindow
    distance_to_slick_km: Optional[float] = None


@dataclass
class ScoredCandidate:
    """Points per factor, a reason per factor, and the total."""

    mmsi: str
    vessel_id: Optional[str]
    name: str
    vessel_type: str
    total: float
    factors: Dict[str, Dict[str, Any]] = dataclass_field(default_factory=dict)
    reasons: List[str] = dataclass_field(default_factory=list)
    distance_to_slick_km: Optional[float] = None

    def factor_points(self, key: str) -> float:
        return float(self.factors[key]["points"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mmsi": self.mmsi,
            "vesselId": self.vessel_id,
            "name": self.name,
            "vesselType": self.vessel_type,
            "totalScore": round(self.total, 3),
            "distanceToSlickKm": (None if self.distance_to_slick_km is None
                                  else round(self.distance_to_slick_km, 3)),
            "factors": {key: self.factors[key] for key in FACTOR_KEYS if key in self.factors},
            "reasons": list(self.reasons),
        }


def _points_reason(key: str, points: float, maximum: float, reason: str) -> str:
    return f"{FACTOR_TITLES[key]}: {reason} [{points:g}/{maximum:g}]"


def score_candidate(
    evidence: CandidateEvidence,
    weights: Optional[EvidenceWeights] = None,
    config: Optional[ScoringConfig] = None,
) -> ScoredCandidate:
    """Compute factor points, per-factor reasons and the total for one vessel.

    Pure function: identical inputs give identical output. Every factor always
    appears in `factors` and `reasons` - zero-point factors explain WHY they
    are zero, because an unexplained omission is indistinguishable from a bug.
    """
    w = weights or EvidenceWeights()
    cfg = config or ScoringConfig()
    compat = evidence.compatibility
    behaviour = evidence.behaviour
    gaps = evidence.gaps
    engaged = bool(compat.inside_region_during_window)

    factors: Dict[str, Dict[str, Any]] = {}
    reasons: List[str] = []

    # --- spatial: proximity of the closest IN-WINDOW approach ----------------
    win_distance = compat.min_distance_km_during_window
    if win_distance is None:
        spatial_fraction = 0.0
        spatial_reason = "no observed position during the release window"
        detail: Dict[str, Any] = {"minDistanceKmDuringWindow": None}
    elif win_distance <= 0.0:
        spatial_fraction = 1.0
        spatial_reason = "inside the estimated origin region during the window"
        detail = {"minDistanceKmDuringWindow": 0.0}
    else:
        spatial_fraction = max(0.0, 1.0 - win_distance / cfg.spatial_falloff_km)
        detail = {"minDistanceKmDuringWindow": round(win_distance, 3)}
        if spatial_fraction > 0.0:
            spatial_reason = (f"closest in-window approach {win_distance:.1f} km, "
                              f"decaying to zero at {cfg.spatial_falloff_km:.0f} km")
        else:
            spatial_reason = (f"closest in-window approach {win_distance:.1f} km - beyond "
                              f"the {cfg.spatial_falloff_km:.0f} km falloff, no spatial "
                              "evidence")
    detail["falloffKm"] = cfg.spatial_falloff_km
    spatial_points = round(w.spatial * spatial_fraction, 3)
    factors["spatial"] = {"points": spatial_points, "maxPoints": w.spatial, "detail": detail}
    reasons.append(_points_reason("spatial", spatial_points, w.spatial, spatial_reason))

    # --- gap: feasibility x relevance, capped --------------------------------
    gap_value = 0.0
    gap_detail: List[Dict[str, Any]] = []
    for fact in gaps.gaps:
        contribution = 0.0
        if fact.feasible is not None and fact.relevance > 0.0 and fact.feasible:
            contribution = min(cfg.gap_relevance_cap, fact.relevance)
        gap_value += contribution
        gap_detail.append({
            "start": fact.start_iso,
            "feasible": fact.feasible,
            "relevance": round(fact.relevance, 4),
            "contribution": round(contribution, 4),
        })
    gap_points = round(w.gap * min(1.0, gap_value), 3)
    relevant_gaps = [f for f in gaps.gaps if f.relevance > 0.0]
    if not gaps.has_gap:
        gap_reason = "no AIS gap - the absence of a gap is not evidence either"
    elif not relevant_gaps:
        gap_reason = "gap present but none relevant to the window and origin region"
    elif gap_points <= 0.0:
        infeasible = [f for f in relevant_gaps if f.feasible is False]
        gap_reason = ("relevant gap but physically impossible to traverse "
                      f"({infeasible[0].implied_speed_kn:.1f} kn required vs "
                      f"{infeasible[0].cap_speed_kn:.1f} kn cap)"
                      if infeasible else "relevant gap contributed no feasible evidence")
    else:
        best = max(relevant_gaps, key=lambda f: f.relevance)
        gap_reason = (f"AIS gap of {best.duration_hours:.1f} h overlaps the window and is "
                      f"traversable at {best.implied_speed_kn:.1f} kn - weak, capped evidence")
    factors["gap"] = {"points": gap_points, "maxPoints": w.gap,
                      "detail": {"value": round(min(1.0, gap_value), 4),
                                 "capPerGap": cfg.gap_relevance_cap, "gaps": gap_detail}}
    reasons.append(_points_reason("gap", gap_points, w.gap, gap_reason))

    # --- trajectory: plausible motion correlated with the region -------------
    fraction = compat.plausible_segment_fraction
    trajectory_points = round(w.trajectory * (1.0 if engaged else 0.0) * fraction, 3)
    if engaged:
        trajectory_reason = (f"movement through the region during the window is physically "
                             f"plausible ({compat.plausible_segments_in_window}/"
                             f"{compat.segments_in_window} in-window segments within the "
                             f"{compat.speed_cap_kn:.0f} kn cap)")
    else:
        trajectory_reason = ("no transit of the origin region during the window - no "
                             "course correlation to score")
    factors["trajectory"] = {"points": trajectory_points, "maxPoints": w.trajectory,
                             "detail": {"plausibleSegmentFraction": round(fraction, 4),
                                        "engaged": engaged}}
    reasons.append(_points_reason("trajectory", trajectory_points, w.trajectory,
                                  trajectory_reason))

    # --- behaviour: own-baseline anomaly, gated on presence ------------------
    behaviour_points = round(w.behaviour * behaviour.scored_anomaly, 3)
    if not engaged:
        if behaviour.is_anomaly:
            behaviour_reason = (f"behaviour anomaly {behaviour.raw_anomaly:.2f} "
                                f"({behaviour.description}) but OUTSIDE the origin region "
                                "during the window - context only, not evidence")
        else:
            behaviour_reason = (f"behaviour {behaviour.description}; no presence in the "
                                "region to correlate with")
    elif behaviour.raw_anomaly > 0.0:
        behaviour_reason = (f"own-baseline anomaly {behaviour.raw_anomaly:.2f} while "
                            f"present in the region ({behaviour.description})")
    else:
        behaviour_reason = "behaviour consistent with own baseline during the window"
    factors["behaviour"] = {"points": behaviour_points, "maxPoints": w.behaviour,
                            "detail": {"rawAnomaly": round(behaviour.raw_anomaly, 4),
                                       "scoredAnomaly": round(behaviour.scored_anomaly, 4),
                                       "scoredEligible": behaviour.scored_eligible,
                                       "description": behaviour.description}}
    reasons.append(_points_reason("behaviour", behaviour_points, w.behaviour,
                                  behaviour_reason))

    # --- temporal: presence inside the region while the window was open ------
    temporal_points = round(w.temporal * (1.0 if engaged else 0.0), 3)
    relation = compat.inside_region_relation
    if engaged:
        temporal_reason = ("present inside the origin region while the release "
                           "window was open")
    elif relation == "after_window":
        temporal_reason = (f"enters the origin region only AFTER the window closed at "
                           f"{evidence.window.end_iso} - right place, wrong time")
    elif relation == "before_window":
        temporal_reason = (f"inside the origin region only BEFORE the window opened at "
                           f"{evidence.window.start_iso} - wrong time")
    elif compat.inside_region_anytime:
        temporal_reason = "passes through the origin region outside the window hours"
    else:
        temporal_reason = "never observed inside the origin region during the window"
    factors["temporal"] = {"points": temporal_points, "maxPoints": w.temporal,
                           "detail": {"insideRegionDuringWindow": engaged,
                                      "relation": relation}}
    reasons.append(_points_reason("temporal", temporal_points, w.temporal, temporal_reason))

    total = round(sum(factors[key]["points"] for key in FACTOR_KEYS), 3)
    return ScoredCandidate(
        mmsi=evidence.mmsi, vessel_id=evidence.vessel_id, name=evidence.name,
        vessel_type=evidence.vessel_type, total=total, factors=factors, reasons=reasons,
        distance_to_slick_km=evidence.distance_to_slick_km,
    )