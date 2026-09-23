"""ABYSS - shared time helpers for the intelligence service.

PURPOSE
    Phases 5-11 all reason about the SAME release window and observation time.
    One parser keeps "2026-03-13T10:00:00Z" meaning the same epoch everywhere:
    a one-hour drift between modules would silently misplace the window and
    corrupt every temporal judgement built on top of it.

WHAT IT IS NOT
    Not a timezone library. The demo contract is ISO-8601 with a trailing 'Z'
    (or an explicit +00:00 offset). Naive timestamps are treated as UTC,
    mirroring the Phase 3 cleaning policy; anything unparseable raises
    ValueError - a wrong window must fail loudly, never default quietly.

ALSO HERE
    ReleaseWindow: the validated candidate release window carried through the
    hindcast, the compatibility filter, the gap analysis and the scoring engine
    so there is exactly one definition of "during the window".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

__all__ = ["parse_iso_z", "iso_z", "epoch_seconds", "ReleaseWindow"]


def parse_iso_z(value: str) -> datetime:
    """Parse an ISO-8601 timestamp to an aware UTC datetime.

    Accepts a trailing 'Z' (case-insensitive) or an explicit offset. Naive input
    is assumed UTC - recorded in the Phase 3 policy - and never rejected
    silently, because dropping the assumption would shift every downstream
    comparison by local offset hours.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"timestamp must be a non-empty ISO-8601 string, got {value!r}")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"timestamp {value!r} is not ISO-8601 parseable") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_z(value: datetime) -> str:
    """Format an aware datetime as the demo's canonical `...Z` string."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def epoch_seconds(value: str) -> int:
    """Integer epoch seconds for an ISO-8601 timestamp (UTC)."""
    return int(parse_iso_z(value).timestamp())


@dataclass(frozen=True)
class ReleaseWindow:
    """The CANDIDATE release window (a prior input), validated once.

    The hindcast integrates the drift field backwards across this window; the
    compatibility filter asks whether a vessel was inside the estimated origin
    region DURING it. It is reported downstream as an estimate with provenance,
    never as a proven fact (docs/methodology.md).
    """

    start_epoch: int
    end_epoch: int
    start_iso: str
    end_iso: str
    source: str = "candidate release window (prior input)"

    def __post_init__(self) -> None:
        if self.end_epoch <= self.start_epoch:
            raise ValueError(
                f"release window must be non-empty: start {self.start_iso} "
                f"must precede end {self.end_iso}"
            )

    def contains(self, epoch: int) -> bool:
        """Inclusive containment test in epoch seconds."""
        return self.start_epoch <= epoch <= self.end_epoch

    def duration_hours(self) -> float:
        return (self.end_epoch - self.start_epoch) / 3600.0

    def hours_before(self, observed_epoch: int) -> Dict[str, float]:
        """Ages in hours of the window boundaries relative to the observation."""
        return {
            "start": round((observed_epoch - self.start_epoch) / 3600.0, 4),
            "end": round((observed_epoch - self.end_epoch) / 3600.0, 4),
        }

    def describe(self) -> Dict[str, Any]:
        return {
            "start": self.start_iso,
            "end": self.end_iso,
            "durationHours": round(self.duration_hours(), 4),
            "source": self.source,
        }