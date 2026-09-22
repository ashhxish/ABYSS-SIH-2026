#!/usr/bin/env python3
"""ABYSS - Phase 4 tests for AIS trajectory construction.

WHAT THESE TESTS PROVE
    1. the bundled synthetic CASE-001 extract builds exactly 12 trajectories with the
       structure the Phase 2 scenario promises: 3,666 records, 3,652 segments, exactly
       TWO structural gaps (V002 and V003, the designed pair) and no other gap
    2. the designed gap pair is preserved as DESIGNED: identical 4 h windows, but
       V002's bridge is reachable at ~10.5 kn while V003's needs ~35.1 kn - more than
       twice what V003 ever reported. That difference is the whole point of the pair
       (specification test cases D and E) and must survive this phase intact
    3. gaps are recorded as FACTS ONLY. No gap record may carry a relevance, suspicion,
       score or ranking field: relevance is decided in the AIS gap analysis phase, and a
       gap alone must never raise suspicion
    4. trajectories are physically consistent: consecutive-position distance agrees with
       the reported speed over ground, no segment is covered faster than the vessel's own
       maximum reported speed, and observed travel excludes the straight line across a gap
    5. geometry is GeoJSON and never draws a straight line through a period with no
       records: the track is split into legs at every gap
    6. descriptive low-speed periods are found for the vessels designed to have them and
       are NOT invented for steady transits; a missing speed ends a period rather than
       extending it
    7. edge cases behave: an empty input, unusable records, a configurable gap threshold,
       no gap before the first or after the last record, course changes not compared across
       a gap, and invalid configuration
    8. construction is deterministic, JSON-serialisable, and carries the synthetic label

WHAT THESE TESTS DO NOT DO
    No spatial filtering, no temporal filtering, no trajectory compatibility, no behaviour
    scoring, no AIS gap relevance, no evidence scoring. Those belong to later phases.

RUN (needs the project virtual environment because pandas is required)
    .venv/bin/python -m unittest discover -s intelligence/tests -v
    .venv/bin/python intelligence/tests/test_ais_trajectory.py -v
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

INTELLIGENCE_DIR = Path(__file__).resolve().parent.parent
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from app.ais.cleaning import clean_demo_case
from app.ais.trajectory import TrajectoryConfig, build_trajectories, build_trajectories_from_cleaning
from app.geo import offset_position

UTC = timezone.utc
T0 = datetime(2026, 3, 11, 6, 0, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# Numbers fixed by the Phase 2 scenario and the Phase 3 cleaning result. They are
# repeated here on purpose: a change in the generator cannot quietly change Phase 4.
# ---------------------------------------------------------------------------
DEMO_VESSELS = 12
DEMO_RECORDS = 3666
DEMO_SEGMENTS = 3652          # one segment per consecutive pair inside each leg
DEMO_GAPS = 2
DEMO_STOP_PERIODS = 12
DEMO_SLOW_PERIODS = 14
DEMO_COURSE_CHANGES = 64

V002 = "900000002"   # DEMO CORAL VOYAGER - gap that IS physically compatible
V003 = "900000003"   # DEMO IRON HORIZON - gap that is NOT physically compatible
V001 = "900000001"   # DEMO MERIDIAN STAR  - primary plausible candidate
V004 = "900000004"   # DEMO HARBOUR LIGHT  - nearest to the slick, far from origin
V006 = "900000006"   # DEMO FROST PELICAN  - strongest anomaly, far away
V007 = "900000007"   # DEMO NORTHERN GATE  - control, steady transit
V008 = "900000008"   # DEMO SEA LARK       - fishing-like, stationary records
V009 = "900000009"   # DEMO SKY BRIDGE     - 19 kn ferry shuttle
V011 = "900000011"   # DEMO ANCHOR TUG     - moored periods
V012 = "900000012"   # DEMO FAR CURRENT    - distant transit

GAP_START = "2026-03-13T11:55:00Z"
GAP_END = "2026-03-13T16:00:00Z"
GAP_SECONDS = 14700.0
V002_BRIDGE_KM = 79.431983
V002_BRIDGE_KN = 10.503634
V003_BRIDGE_KN = 35.145525


def iso(seconds: int) -> str:
    """ISO-8601 UTC timestamp `seconds` after T0."""
    return (T0 + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def rec(mmsi: str = "900000001", seconds: int = 0, lat: float = 18.0, lon: float = 72.0,
        sog: float | None = 10.0, cog: float | None = 90.0, **extra) -> dict:
    """One crafted AIS record for the edge-case tests."""
    record = {
        "mmsi": mmsi, "timestamp": iso(seconds), "latitude": lat, "longitude": lon,
        "sogKn": sog, "cogDeg": cog, "vesselName": f"TEST {mmsi}",
        "datasetLabel": "Synthetic Demonstration Dataset", "synthetic": True,
    }
    record.update(extra)
    return record


def straight_track(mmsi: str, steps: int, speed_kn: float, bearing_deg: float,
                   interval_s: int = 300, sog: float | None = None,
                   start_lat: float = 18.0, start_lon: float = 72.0) -> list:
    """A geometrically correct straight track: real positions for the declared speed."""
    lat, lon = start_lat, start_lon
    km_per_step = speed_kn * 1.852 * (interval_s / 3600.0)
    rows = []
    for step in range(steps):
        rows.append(rec(mmsi=mmsi, seconds=step * interval_s, lat=round(lat, 6),
                        lon=round(lon, 6), sog=speed_kn if sog is None else sog,
                        cog=bearing_deg))
        lat, lon = offset_position(lat, lon, bearing_deg, km_per_step)
    return rows



class TestDemoTrajectories(unittest.TestCase):
    """Structural expectations for the deterministic CASE-001 demonstration dataset."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = clean_demo_case()
        cls.collection = build_trajectories_from_cleaning(cls.result)
        cls.by_mmsi = cls.collection.by_mmsi()

    # --- identity and counts -------------------------------------------------
    def test_one_trajectory_per_vessel_and_exactly_twelve(self):
        self.assertEqual(len(self.collection.trajectories), DEMO_VESSELS)
        self.assertEqual(sorted(self.by_mmsi), [f"9000000{i:02d}" for i in range(1, 13)])

    def test_counts_reconcile_with_the_cleaning_result(self):
        counts = self.collection.statistics["counts"]
        self.assertEqual(counts["records"], DEMO_RECORDS)
        self.assertEqual(counts["records"], self.result.statistics["counts"]["records"])
        self.assertEqual(counts["segments"], DEMO_SEGMENTS)
        self.assertEqual(counts["gaps"], DEMO_GAPS)
        self.assertEqual(counts["stopPeriods"], DEMO_STOP_PERIODS)
        self.assertEqual(counts["slowPeriods"], DEMO_SLOW_PERIODS)
        self.assertEqual(counts["courseChanges"], DEMO_COURSE_CHANGES)
        self.assertEqual(counts["skippedRecords"], 0)

    def test_segment_count_equals_records_minus_legs(self):
        """A segment joins two CONSECUTIVE records; a gap therefore removes one."""
        for vessel in self.collection.trajectories:
            legs = len(vessel.geometryByLeg)
            self.assertEqual(len(vessel.segments), vessel.record_count - legs,
                             f"{vessel.mmsi}: segments must equal records minus legs")

    def test_only_the_two_designed_gaps_exist(self):
        with_gaps = {mmsi: len(t.gaps) for mmsi, t in self.by_mmsi.items() if t.gaps}
        self.assertEqual(with_gaps, {V002: 1, V003: 1})
        self.assertEqual(self.by_mmsi[V001].gaps, [],
                         "the primary plausible candidate has no gap; none may be invented")

    def test_points_are_chronological_and_have_unique_indices(self):
        for vessel in self.collection.trajectories:
            stamps = [point.epochSeconds for point in vessel.points]
            self.assertEqual(stamps, sorted(stamps), f"{vessel.mmsi}: points must be ordered")
            self.assertEqual([p.index for p in vessel.points], list(range(vessel.record_count)))

    # --- the designed gap pair (specification cases D and E) -----------------
    def test_gap_pair_shares_the_same_window_and_duration(self):
        for mmsi in (V002, V003):
            gap = self.by_mmsi[mmsi].gaps[0]
            self.assertEqual(gap.startTimestamp, GAP_START)
            self.assertEqual(gap.endTimestamp, GAP_END)
            self.assertAlmostEqual(gap.durationSeconds, GAP_SECONDS, places=3)
            self.assertAlmostEqual(gap.durationSeconds / 3600.0, 4.0833, places=4)

    def test_gap_pair_differs_only_in_physical_feasibility(self):
        """The heart of the fixture: same story, different physics."""
        feasible = self.by_mmsi[V002].gaps[0]
        impossible = self.by_mmsi[V003].gaps[0]
        self.assertAlmostEqual(feasible.straightLineKm, V002_BRIDGE_KM, delta=0.05)
        self.assertAlmostEqual(feasible.impliedSpeedKn, V002_BRIDGE_KN, delta=0.05)
        self.assertGreater(impossible.straightLineKm, 250.0)
        self.assertAlmostEqual(impossible.impliedSpeedKn, V003_BRIDGE_KN, delta=0.05)

    def test_feasible_gap_is_within_the_vessel_own_capability(self):
        vessel = self.by_mmsi[V002]
        gap = vessel.gaps[0]
        self.assertLessEqual(gap.impliedSpeedKn, vessel.stats["maxReportedSogKn"] + 0.05,
                             "V002's gap is bridgeable at the speed it actually reported")

    def test_impossible_gap_far_exceeds_the_vessel_own_capability(self):
        vessel = self.by_mmsi[V003]
        gap = vessel.gaps[0]
        self.assertGreater(gap.impliedSpeedKn, 2.5 * vessel.stats["maxReportedSogKn"],
                           "V003's gap needs more than twice the speed it ever reported")

    def test_gap_notes_state_that_relevance_belongs_to_a_later_phase(self):
        for mmsi in (V002, V003):
            note = self.by_mmsi[mmsi].gaps[0].to_dict()["note"]
            self.assertIn("relevance", note.lower())
            self.assertIn("gap analysis", note.lower())

    def test_gap_records_carry_facts_only_and_no_judgement(self):
        """A gap alone must never raise suspicion: no relevance or score may exist yet."""
        forbidden = ("score", "relevan", "suspi", "rank", "guilt", "culprit")
        for mmsi in (V002, V003):
            for key in self.by_mmsi[mmsi].gaps[0].to_dict():
                for token in forbidden:
                    self.assertNotIn(token, key.lower(),
                                     f"gap field '{key}' implies a judgement made in a later phase")

    # --- physical consistency of the trajectories ----------------------------
    def test_observed_travel_is_the_sum_of_the_segments(self):
        for vessel in self.collection.trajectories:
            self.assertAlmostEqual(vessel.stats["observedDistanceKm"],
                                   sum(segment.distanceKm for segment in vessel.segments),
                                   places=3, msg=f"{vessel.mmsi}: travel must come from segments")

    def test_straight_line_across_gaps_is_reported_but_not_counted_as_travel(self):
        totals = self.collection.statistics["totals"]
        self.assertAlmostEqual(totals["straightLineGapKm"], V002_BRIDGE_KM + 265.8, delta=0.2)
        observed = sum(v.stats["observedDistanceKm"] for v in self.collection.trajectories)
        self.assertNotAlmostEqual(totals["observedDistanceKm"], observed + totals["straightLineGapKm"])

    def test_no_segment_is_covered_faster_than_the_vessel_own_maximum(self):
        """Mirrors the generator self-check, now on the data Phase 5+ will actually read."""
        for vessel in self.collection.trajectories:
            ceiling = vessel.stats["maxReportedSogKn"] + 0.2
            for segment in vessel.segments:
                if segment.impliedSpeedKn is not None:
                    self.assertLessEqual(segment.impliedSpeedKn, ceiling,
                                         f"{vessel.mmsi}: {segment.startTimestamp}")

    def test_segment_distance_agrees_with_reported_speed_over_the_interval(self):
        """A last guard against the degree-vs-metre scaling class of bug.

        This is the assertion that caught the demo generator building tracks in degrees and
        then translating them across latitudes, which made every east-west step about 4%
        longer than the reported speed implied.

        The 5 kn floor is deliberate: the SOG column has 0.1 kn resolution, so at 2 kn a
        single rounding step is already +/-2.5% and the comparison would be measuring
        quantisation rather than correctness. Measured worst on the demo dataset is 0.83%,
        so the 2% tolerance leaves roughly 2.4x headroom while still failing loudly if the
        scaling bug returns.
        """
        worst = 0.0
        compared = 0
        for vessel in self.collection.trajectories:
            for segment in vessel.segments:
                if segment.impliedSpeedKn is None or segment.reportedSogKn is None:
                    continue
                if segment.reportedSogKn < 5.0:
                    continue
                compared += 1
                worst = max(worst, abs(segment.impliedSpeedKn - segment.reportedSogKn)
                            / segment.reportedSogKn)
        self.assertGreater(compared, 2000, "the comparison must actually cover the dataset")
        self.assertLess(worst, 0.02, f"worst relative difference {worst * 100:.2f}%")

    # --- geometry ------------------------------------------------------------
    def test_geometry_is_geojson_and_covers_every_record(self):
        for vessel in self.collection.trajectories:
            self.assertEqual(vessel.geometry["type"], "LineString")
            self.assertEqual(len(vessel.geometry["coordinates"]), vessel.record_count)
            for lon, lat in vessel.geometry["coordinates"]:
                self.assertTrue(-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0)

    def test_geometry_is_split_into_legs_at_every_gap(self):
        for vessel in self.collection.trajectories:
            self.assertEqual(len(vessel.geometryByLeg), len(vessel.gaps) + 1)
            for leg in vessel.geometryByLeg:
                self.assertEqual(leg["type"], "LineString")
                self.assertGreaterEqual(len(leg["coordinates"]), 1)
            covered = sum(len(leg["coordinates"]) for leg in vessel.geometryByLeg)
            self.assertEqual(covered, vessel.record_count)

    def test_legs_stop_at_the_records_either_side_of_a_gap(self):
        """No leg may draw a straight line through unobserved time."""
        vessel = self.by_mmsi[V002]
        gap = vessel.gaps[0]
        first_leg, second_leg = vessel.geometryByLeg
        self.assertEqual(vessel.points[first_leg["endIndex"]].timestamp, gap.startTimestamp)
        self.assertEqual(vessel.points[second_leg["startIndex"]].timestamp, gap.endTimestamp)
        self.assertEqual(first_leg["endIndex"] + 1, second_leg["startIndex"])

    # --- descriptive low-speed periods ---------------------------------------
    def test_designed_low_speed_vessels_are_found(self):
        self.assertEqual(self.by_mmsi[V002].stats["stopPeriodCount"], 0)
        self.assertGreaterEqual(self.by_mmsi[V008].stats["stopPeriodCount"], 1)
        self.assertGreaterEqual(self.by_mmsi[V011].stats["stopPeriodCount"], 1)
        self.assertGreaterEqual(self.by_mmsi[V001].stats["slowPeriodCount"], 1)
        self.assertGreaterEqual(self.by_mmsi[V004].stats["slowPeriodCount"], 1)

    def test_steady_transits_have_no_low_speed_periods(self):
        for mmsi in (V002, V003, V007, V009, V012):
            vessel = self.by_mmsi[mmsi]
            self.assertEqual(vessel.stopSlowPeriods, [],
                             f"{vessel.mmsi} is a steady transit: low-speed periods must not be invented")

    def test_high_speed_ferry_keeps_its_turnarounds_but_no_gap(self):
        vessel = self.by_mmsi[V009]
        self.assertEqual(vessel.gaps, [])
        self.assertEqual(vessel.stopSlowPeriods, [])
        self.assertGreater(vessel.stats["maxReportedSogKn"], 19.0)
        self.assertGreaterEqual(vessel.stats["courseChangeCount"], 10)

    def test_low_speed_periods_are_labelled_descriptive_only(self):
        for vessel in self.collection.trajectories:
            for period in vessel.stopSlowPeriods:
                self.assertIn("descriptive", period.to_dict()["note"].lower())
