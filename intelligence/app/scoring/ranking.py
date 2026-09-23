"""ABYSS - candidate ranking with counterfactual explanations (Phase 10b).

PURPOSE
    Order scored candidates deterministically and attach, to EVERY entry, a
    counterfactual: which vessel it displaced or was displaced by, and by which
    factor margins. The rank-1 entry additionally explains why the vessel
    NEAREST to the observed slick did not rank first - the slick-proximity trap
    that docs/demo-scenario.md calls specification case G.

ORDERING RULE
    Descending total score; ties broken by ASCENDING MMSI (the stable, data-
    supplied identifier). Ties are surfaced explicitly rather than hidden: a
    group of equal scores ordered by identifier is honest about how much the
    evidence can and cannot separate.

WHAT IT IS NOT
    Ranking is an evidence ordering for investigation support. It never implies
    guilt, and it never re-scores anything - scoring is the engine's job only.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

if __package__ in (None, ""):  # executed directly as a script
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.scoring.engine import FACTOR_KEYS, ScoredCandidate
else:
    from app.scoring.engine import FACTOR_KEYS, ScoredCandidate

__all__ = ["RankedCandidate", "RankingResult", "rank_candidates"]

ORDERING_RULE = (
    "descending total score; ties broken by ascending MMSI "
    "(deterministic - equal evidence yields equal scores)"
)


@dataclass
class RankedCandidate:
    """One scored candidate plus its rank and counterfactual explanation."""

    rank: int
    scored: ScoredCandidate
    counterfactual: Optional[Dict[str, Any]] = None

    @property
    def total(self) -> float:
        return self.scored.total

    @property
    def mmsi(self) -> str:
        return self.scored.mmsi

    def to_dict(self) -> Dict[str, Any]:
        payload = self.scored.to_dict()
        payload["rank"] = self.rank
        payload["counterfactual"] = self.counterfactual
        return payload


@dataclass
class RankingResult:
    """The ordered list plus the ordering rule and any tie groups."""

    entries: List[RankedCandidate] = dataclass_field(default_factory=list)
    ordering_rule: str = ORDERING_RULE
    notes: List[str] = dataclass_field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.entries)

    def by_mmsi(self) -> Dict[str, RankedCandidate]:
        return {entry.mmsi: entry for entry in self.entries}

    def tie_groups(self) -> List[List[str]]:
        """MMSI groups that share a total score (2+ members only)."""
        groups: Dict[float, List[str]] = {}
        for entry in self.entries:
            groups.setdefault(entry.total, []).append(entry.mmsi)
        return [mmsis for mmsis in groups.values() if len(mmsis) >= 2]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "orderingRule": self.ordering_rule,
            "tieGroups": self.tie_groups(),
            "notes": list(self.notes),
            "entries": [entry.to_dict() for entry in self.entries],
        }


def _factor_deltas(above: ScoredCandidate, below: ScoredCandidate) -> Dict[str, float]:
    """Points the higher-ranked candidate held OVER the lower one, per factor."""
    deltas = {}
    for key in FACTOR_KEYS:
        delta = round(above.factor_points(key) - below.factor_points(key), 3)
        if delta != 0.0:
            deltas[key] = delta
    return deltas


def _counterfactual_text(above: RankedCandidate, below: RankedCandidate) -> str:
    deltas = _factor_deltas(above.scored, below.scored)
    if not deltas:
        return (f"Scored equally with {above.scored.name} ({above.total:g} vs "
                f"{below.total:g}); ordered after it by the MMSI tie-break "
                "(deterministic, not evidential)")
    parts = ", ".join(f"{key} +{value:g}" for key, value in
                      sorted(deltas.items(), key=lambda kv: -abs(kv[1])))
    return (f"Ranked below {above.scored.name} ({above.total:g} vs {below.total:g}): "
            f"{above.scored.name} led on {parts}")


def rank_candidates(scored: Sequence[ScoredCandidate]) -> RankingResult:
    """Order candidates and attach a counterfactual to every entry.

    `scored` must contain distinct MMSIs; duplicates would make the tie-break
    unstable and are rejected rather than silently deduplicated.
    """
    mmsis = [candidate.mmsi for candidate in scored]
    if len(set(mmsis)) != len(mmsis):
        raise ValueError("duplicate MMSI in scored candidates - ranking would be unstable")

    ordered = sorted(scored, key=lambda c: (-round(c.total, 6), c.mmsi))
    entries = [RankedCandidate(rank=index + 1, scored=candidate)
               for index, candidate in enumerate(ordered)]

    nearest_index: Optional[int] = None
    if entries:
        with_distance = [(i, e) for i, e in enumerate(entries)
                         if e.scored.distance_to_slick_km is not None]
        if with_distance:
            nearest_index = min(with_distance,
                                key=lambda pair: pair[1].scored.distance_to_slick_km)[0]

    for index, entry in enumerate(entries):
        if index == 0:
            if nearest_index is not None and nearest_index != 0:
                nearest = entries[nearest_index]
                entry.counterfactual = {
                    "againstMmsi": nearest.mmsi,
                    "againstName": nearest.scored.name,
                    "text": (
                        f"{nearest.scored.name} is nearest to the observed slick "
                        f"({nearest.scored.distance_to_slick_km:.1f} km) yet ranked "
                        f"{nearest.rank} with {nearest.total:g} points against "
                        f"{entry.total:g}: slick proximity is not release proximity - "
                        f"{entry.scored.name} was inside the origin region during the "
                        "window, where proximity to the slick scores nothing"
                    ),
                    "factorDeltas": _factor_deltas(entry.scored, nearest.scored),
                }
            else:
                entry.counterfactual = {
                    "againstMmsi": None,
                    "againstName": None,
                    "text": ("ranked first; the vessel nearest to the observed slick "
                             "is itself the top candidate"),
                    "factorDeltas": {},
                }
        else:
            above = entries[index - 1]
            entry.counterfactual = {
                "againstMmsi": above.mmsi,
                "againstName": above.scored.name,
                "text": _counterfactual_text(above, entry),
                "factorDeltas": _factor_deltas(above.scored, entry.scored),
            }

    notes = [
        ORDERING_RULE,
        "an equal score is a real result: the evidence does not separate those "
        "candidates, and the identifier tie-break is a display choice, not a finding",
        "ranking orders evidence for investigation support; it never establishes "
        "legal responsibility",
    ]
    return RankingResult(entries=entries, notes=notes)