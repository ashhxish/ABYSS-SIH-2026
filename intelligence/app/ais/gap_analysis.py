"""ABYSS - AIS gap analysis (Phase 9).

PURPOSE
    Judge each structural AIS gap against the reconstructed origin region and
    the release window: COULD the vessel have crossed the region while silent
    (feasibility, at a speed it could plausibly make) and DID the gap overlap
    the window near the region (relevance)? Output: per-gap FACTS, a feasibility
    judgement and a relevance value in [0, 1]; the scoring engine maps those
    onto the configured gap weight.

THE GOLDEN RULE (docs/methodology.md section 5)
    A gap alone NEVER raises suspicion - it can only fail to reduce it:
    no gap -> zero evidence ("absence of a gap is not evidence" either);
    irrelevant or infeasible gap -> zero; relevant + feasible -> at most a
    small capped share of the total score.

WHAT IT IS NOT
    It never asserts the vessel WAS inside the region during the gap - only
    whether crossing was physically possible. No points are assigned here.
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

__all__ = ["GapAnalysisConfig", "GapFact", "GapAssessment", "analyse_gaps"]


@dataclass(frozen=True)
class GapAnalysisConfig:
    """Feasibility/relevance thresholds. Prototype values, all reported."""

    feasibility_margin: float = 1.3       # x the vessel's own max reported SOG
    min_feasible_speed_kn: float = 5.0    # floor when own max is unknown
    global_max_speed_kn: float = 60.0     # cleaning ceiling (never exceed it)
    endpoint_near_region_km: float = 30.0

    def __post_init__(self) -> None:
        if self.feasibility_margin < 1.0:
            raise ValueError("feasibility_margin must be >= 1.0")
        if self.min_feasible_speed_kn <= 0:
            raise ValueError("min_feasible_speed_kn must be > 0")
        if self.global_max_speed_kn <= 0:
            raise ValueError("global_max_speed_kn must be > 0")
        if self.endpoint_near_region_km <= 0:
            raise ValueError("endpoint_near_region_km must be > 0")

    def describe(self) -> Dict[str, Any]:
        return {
            "feasibilityMargin": self.feasibility_margin,
            "minFeasibleSpeedKn": self.min_feasible_speed_kn,
            "globalMaxSpeedKn": self.global_max_speed_kn,
            "endpointNearRegionKm": self.endpoint_near_region_km,
        }


@dataclass
class GapFact:
    """One structural gap: measured facts plus feasibility/relevance judgements."""

    start_iso: str
    end_iso: str
    duration_hours: float
    straight_line_km: float
    implied_speed_kn: Optional[float]
    overlaps_window: bool
    overlap_hours: float
    gap_fraction_in_window: float
    before: Dict[str, Any] = dataclass_field(default_factory=dict)
    after: Dict[str, Any] = dataclass_field(default_factory=dict)
    endpoint_near_region: bool = False
    cap_speed_kn: float = 0.0
    feasible: Optional[bool] = None
    relevance: float = 0.0
    reasons: List[str] = dataclass_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": self.start_iso,
            "end": self.end_iso,
            "durationHours": round(self.duration_hours, 4),
            "straightLineKm": round(self.straight_line_km, 3),
            "impliedSpeedKn": (None if self.implied_speed_kn is None
                               else round(self.implied_speed_kn, 3)),
            "overlapsWindow": self.overlaps_window,
            "overlapHours": round(self.overlap_hours, 4),
            "gapFractionInWindow": round(self.gap_fraction_in_window, 4),
            "before": self.before,
            "after": self.after,
            "endpointNearRegion": self.endpoint_near_region,
            "capSpeedKn": round(self.cap_speed_kn, 3),
            "feasible": self.feasible,
            "relevance": round(self.relevance, 4),
            "reasons": list(self.reasons),
            "note": "a gap alone never raises suspicion (docs/methodology.md)",
        }


@dataclass
class GapAssessment:
    """All gaps of one vessel plus aggregate judgements for the engine."""

    mmsi: str
    gaps: List[GapFact] = dataclass_field(default_factory=list)
    cap_speed_kn: float = 0.0
    notes: List[str] = dataclass_field(default_factory=list)

    @property
    def has_gap(self) -> bool:
        return bool(self.gaps)

    @property
    def any_feasible(self) -> bool:
        return any(g.feasible is True for g in self.gaps)

    @property
    def any_relevant(self) -> bool:
        return any(g.relevance > 0.0 for g in self.gaps)

    @property
    def best_evidence_value(self) -> float:
        """Largest single-gap evidence value: feasibility x relevance (0..1)."""
        return max(((1.0 if g.feasible else 0.0) * g.relevance for g in self.gaps),
                   default=0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mmsi": self.mmsi,
            "hasGap": self.has_gap,
            "gapCount": len(self.gaps),
            "capSpeedKn": round(self.cap_speed_kn, 3),
            "anyFeasible": self.any_feasible,
            "anyRelevant": self.any_relevant,
            "bestEvidenceValue": round(self.best_evidence_value, 4),
            "gaps": [gap.to_dict() for gap in self.gaps],
            "notes": list(self.notes),
        }


def analyse_gaps(
    trajectory: VesselTrajectory,
    origin: OriginEstimate,
    window: ReleaseWindow,
    config: Optional[GapAnalysisConfig] = None,
) -> GapAssessment:
    """Judge every structural gap of one trajectory.

    Feasibility asks: at the vessel's own maximum plausible speed, could the
    gap's endpoints be bridged? Relevance asks: did the gap overlap the window
    with an endpoint near the origin region? Relevance alone never scores - the
    engine multiplies it by feasibility AND caps it.
    """
    cfg = config or GapAnalysisConfig()
    assessment = GapAssessment(mmsi=trajectory.mmsi)

    own_max = trajectory.stats.get("maxReportedSogKn")
    if own_max:
        cap = min(cfg.global_max_speed_kn,
                  max(float(own_max) * cfg.feasibility_margin, cfg.min_feasible_speed_kn))
    else:
        cap = cfg.global_max_speed_kn
    assessment.cap_speed_kn = cap

    for gap in trajectory.gaps:
        start_epoch = epoch_seconds(gap.startTimestamp)
        end_epoch = epoch_seconds(gap.endTimestamp)
        duration_hours = gap.durationSeconds / 3600.0
        overlap_seconds = max(0, min(end_epoch, window.end_epoch)
                              - max(start_epoch, window.start_epoch))
        overlap_hours = overlap_seconds / 3600.0
        overlaps = overlap_seconds > 0
        fraction = (overlap_hours / duration_hours) if duration_hours > 0 else 0.0

        before_pos = gap.lastPosition or {}
        after_pos = gap.nextPosition or {}
        before = {"lat": before_pos.get("latitude"), "lon": before_pos.get("longitude"),
                  "timestamp": before_pos.get("timestamp")}
        after = {"lat": after_pos.get("latitude"), "lon": after_pos.get("longitude"),
                 "timestamp": after_pos.get("timestamp")}
        d_before = (origin.distance_to_region_km(before["lat"], before["lon"])
                    if before.get("lat") is not None else float("inf"))
        d_after = (origin.distance_to_region_km(after["lat"], after["lon"])
                   if after.get("lat") is not None else float("inf"))
        before["distanceToRegionKm"] = (None if d_before == float("inf")
                                        else round(d_before, 3))
        after["distanceToRegionKm"] = (None if d_after == float("inf")
                                       else round(d_after, 3))
        before["insideRegion"] = d_before <= 0.0
        after["insideRegion"] = d_after <= 0.0
        endpoint_near = (d_before <= cfg.endpoint_near_region_km
                         or d_after <= cfg.endpoint_near_region_km)

        feasible: Optional[bool] = None
        if gap.impliedSpeedKn is not None:
            feasible = gap.impliedSpeedKn <= cap

        relevance = 0.0
        reasons = [f"gap {gap.startTimestamp} to {gap.endTimestamp} "
                   f"({duration_hours:.2f} h, {gap.straightLineKm:.1f} km straight line)"]
        if gap.impliedSpeedKn is not None:
            reasons.append(f"bridging requires {gap.impliedSpeedKn:.1f} kn against a "
                           f"cap of {cap:.1f} kn (own max "
                           f"{f'{own_max:.1f}' if own_max else 'unknown'} kn x "
                           f"{cfg.feasibility_margin})")
        if feasible is False:
            reasons.append("INFEASIBLE: required speed exceeds what this vessel ever "
                           "reported - the gap cannot hide a transit")
        if not overlaps:
            reasons.append("does not overlap the release window - not relevant")
        elif not endpoint_near:
            reasons.append(f"overlaps the window but both endpoints are further than "
                           f"{cfg.endpoint_near_region_km:.0f} km from the origin region "
                           "- not relevant")
        else:
            near_factor = 1.0 if (d_before <= 0.0 or d_after <= 0.0) else 0.5
            relevance = fraction * near_factor
            reasons.append(f"overlaps the window ({overlap_hours:.2f} h of the gap) with "
                           f"an endpoint {'inside' if near_factor == 1.0 else 'near'} "
                           "the origin region - relevant")

        assessment.gaps.append(GapFact(
            start_iso=gap.startTimestamp, end_iso=gap.endTimestamp,
            duration_hours=duration_hours, straight_line_km=gap.straightLineKm,
            implied_speed_kn=gap.impliedSpeedKn,
            overlaps_window=overlaps, overlap_hours=overlap_hours,
            gap_fraction_in_window=fraction, before=before, after=after,
            endpoint_near_region=endpoint_near, cap_speed_kn=cap,
            feasible=feasible, relevance=relevance, reasons=reasons,
        ))

    if not assessment.gaps:
        assessment.notes.append("no AIS gap in the track; the ABSENCE of a gap is not "
                                "evidence either - gap contribution is 0")
    assessment.notes.append(
        "a gap alone never raises suspicion: it contributes only when relevant to the "
        "window/region AND physically feasible, and the engine caps its share "
        f"(config: {cfg.describe()})"
    )
    return assessment