#!/usr/bin/env python3
"""ABYSS - Phase 9 tests for AIS gap analysis.

WHAT THESE TESTS PROVE
    1. the matched fixture pair behaves as designed. V002 and V003 have the SAME gap
       timing, the SAME 4.08 h duration, both start inside the origin region, and both
       overlap the release window completely - so both are equally RELEVANT (relevance
       1.0). Only physical feasibility separates them: 79.4 km in the gap is 10.5 kn
       against V002's own 13.9 kn cap (feasible), while 265.8 km is 35.1 kn against
       V003's 15.9 kn cap (infeasible). Specification cases D and E
    2. consequence: the pair's evidence value is 1.0 versus 0.0. Relevance WITHOUT
       feasibility is worth nothing, which is the enforcement of "an AIS gap alone must
       never strongly increase suspicion"
    3. the absence of a gap yields zero evidence too, and the module says so explicitly.
       A clean track is not rewarded for being clean (V001, V007)
    4. relevance needs BOTH window overlap AND an endpoint near the region, and the
       sub-cases are distinguished in the reasons: "does not overlap the release window -
       not relevant" versus "overlaps the window but both endpoints are further than
       30 km ... - not relevant"
    5. a gap record carries facts and judgements only - no score, ranking or suspicion
       field - so the boundary between measurement and inference cannot erode silently
    6. crafted cases behave: a gap before the window, a gap between two distant
       endpoints, and a gap with an endpoint merely NEAR the region (half relevance)

WHAT THESE TESTS DO NOT DO
    No points, no scoring, no ranking. Cap speeds and relevance are inputs to Phase 10,
    and the engine's use of them is tested in test_scoring_engine.py.

RUN (needs the project virtual environment)
    .venv/bin/python -m unittest discover -s intelligence/tests -v
    .venv/bin/python intelligence/tests/test_ais_gap_analysis.py -v
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
from app.ais.gap_analysis import GapAnalysisConfig, analyse_gaps
from app.ais.trajectory import build_trajectories_from_cleaning, trajectory_from_records
from app.geo import offset_position
from app.hindcast.origin import estimate_origin
from app.investigation import load_case_inputs

UTC = timezone.utc
T0 = datetime(2026, 3, 11, 6, 0, 0, tzinfo=UTC)

V001, V002, V003 = "900000001", "900000002", "900000003"
V007 = "900000007"

GAP_START = "2026-03-13T11:55:00Z"
GAP_END = "2026-03-13T16:00:00Z"
GAP_DURATION_HOURS = 4.0833
V002_BRIDGE_KM, V002_IMPLIED_KN, V002_CAP_KN = 79.432, 10.504, 13.91
V003_BRIDGE_KM, V003_IMPLIED_KN, V003_CAP_KN = 265.782, 35.146, 15.86
RELEASE_LAT, RELEASE_LON = 18.3, 71.9      # answer-key coordinate, fixtures only
WINDOW_START = "2026-03-13T10:00:00Z"


def iso(seconds: int) -> str:
    return (T0 + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def secs(value: str) -> int:
    return int((datetime.fromisoformat(value.replace("Z", "+00:00")) - T0).total_seconds())


def rec(mmsi: str, timestamp: str, lat: float, lon: float,
        sog: float = 8.0, cog: float = 45.0) -> dict:
    return {"mmsi": mmsi, "timestamp": timestamp, "latitude": lat, "longitude": lon,
            "sogKn": sog, "cogDeg": cog, "vesselName": f"TEST {mmsi}",
            "datasetLabel": "Synthetic Demonstration Dataset", "synthetic": True}


def gapped_track(mmsi: str, lat: float, lon: float, first_iso: str,
                 gap_hours: float, before: int = 6, after: int = 6,
                 interval_s: int = 300, speed_kn: float = 8.0) -> list:
    """A track with ONE structural silence: `before` records, a hole, `after` records."""
    start = secs(first_iso)
    rows = [rec(mmsi, iso(start + k * interval_s), lat, lon, sog=speed_kn)
            for k in range(before)]
    resume = start + (before - 1) * interval_s + int(gap_hours * 3600.0)
    rows += [rec(mmsi, iso(resume + k * interval_s), lat, lon, sog=speed_kn)
             for k in range(after)]
    return rows


class TestDemoGapPair(unittest.TestCase):
    """The V002/V003 matched pair: same gap, different physics."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = load_case_inputs()
        cls.origin = estimate_origin(cls.inputs["slickRing"], cls.inputs["observedAt"],
                                     cls.inputs["window"], cls.inputs["field"])
        cls.window = cls.inputs["window"]
        cls.trajectories = build_trajectories_from_cleaning(clean_demo_case()).by_mmsi()
        cls.assessed = {mmsi: analyse_gaps(trajectory, cls.origin, cls.window)
                        for mmsi, trajectory in cls.trajectories.items()}

    def gap_of(self, mmsi: str):
        assessment = self.assessed[mmsi]
        self.assertEqual(len(assessment.gaps), 1, f"{mmsi} should have exactly one gap")
        return assessment.gaps[0]

    # --- the pair is identical except for feasibility ------------------------
    def test_the_pair_shares_timing_duration_and_region_entry(self):
        feasible, impossible = self.gap_of(V002), self.gap_of(V003)
        for fact in (feasible, impossible):
            self.assertEqual(fact.start_iso, GAP_START)
            self.assertEqual(fact.end_iso, GAP_END)
            self.assertAlmostEqual(fact.duration_hours, GAP_DURATION_HOURS, places=4)
            self.assertTrue(fact.overlaps_window)
            self.assertEqual(fact.gap_fraction_in_window, 1.0)
            self.assertTrue(fact.endpoint_near_region)
            self.assertTrue(fact.before["insideRegion"])

    def test_relevance_is_identical_so_it_cannot_be_the_discriminator(self):
        feasible, impossible = self.gap_of(V002), self.gap_of(V003)
        self.assertEqual(feasible.relevance, 1.0)
        self.assertEqual(impossible.relevance, 1.0)
        self.assertTrue(self.assessed[V003].any_relevant)

    def test_only_the_bridge_distance_and_speed_differ(self):
        feasible, impossible = self.gap_of(V002), self.gap_of(V003)
        self.assertAlmostEqual(feasible.straight_line_km, V002_BRIDGE_KM, delta=0.05)
        self.assertAlmostEqual(impossible.straight_line_km, V003_BRIDGE_KM, delta=0.05)
        self.assertAlmostEqual(feasible.implied_speed_kn, V002_IMPLIED_KN, delta=0.05)
        self.assertAlmostEqual(impossible.implied_speed_kn, V003_IMPLIED_KN, delta=0.05)

    def test_feasibility_is_decided_against_each_vessels_own_speed_cap(self):
        feasible, impossible = self.gap_of(V002), self.gap_of(V003)
        self.assertAlmostEqual(feasible.cap_speed_kn, V002_CAP_KN, delta=0.02)
        self.assertAlmostEqual(impossible.cap_speed_kn, V003_CAP_KN, delta=0.02)
        self.assertIs(feasible.feasible, True)
        self.assertIs(impossible.feasible, False)
        self.assertLess(feasible.implied_speed_kn, feasible.cap_speed_kn)
        self.assertGreater(impossible.implied_speed_kn, impossible.cap_speed_kn)

    def test_the_infeasible_gap_says_so_in_plain_language(self):
        reasons = " ".join(self.gap_of(V003).reasons)
        self.assertIn("INFEASIBLE", reasons)
        self.assertIn("cannot hide a transit", reasons)

    def test_evidence_value_is_feasibility_times_relevance(self):
        self.assertEqual(self.assessed[V002].best_evidence_value, 1.0)
        self.assertEqual(self.assessed[V003].best_evidence_value, 0.0)

    # --- a clean track earns nothing from being clean ------------------------
    def test_a_vessel_without_a_gap_receives_no_gap_evidence(self):
        for mmsi in (V001, V007):
            assessment = self.assessed[mmsi]
            self.assertFalse(assessment.has_gap)
            self.assertEqual(assessment.gaps, [])
            self.assertEqual(assessment.best_evidence_value, 0.0)
            self.assertIn("ABSENCE of a gap is not evidence either",
                          " ".join(assessment.notes))

    def test_every_assessment_states_the_golden_rule(self):
        for mmsi, assessment in self.assessed.items():
            self.assertIn("a gap alone never raises suspicion",
                          " ".join(assessment.notes), mmsi)

    # --- measurement discipline ---------------------------------------------
    @staticmethod
    def _key_names(payload) -> list:
        """Every dict key in a nested payload, lower-cased."""
        names = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                names.append(str(key).lower())
                names.extend(TestDemoGapPair._key_names(value))
        elif isinstance(payload, list):
            for item in payload:
                names.extend(TestDemoGapPair._key_names(item))
        return names

    def test_gap_records_carry_no_score_ranking_or_suspicion_field(self):
        """Field NAMES are checked, not prose: the safety note legitimately says
        'a gap alone never raises suspicion', which is the opposite of a leak."""
        for mmsi, assessment in self.assessed.items():
            for key in self._key_names(assessment.to_dict()):
                for forbidden in ("score", "ranking", "suspicion", "guilt"):
                    self.assertNotIn(forbidden, key, f"{mmsi} leaked field {key!r}")

    def test_only_the_two_designed_vessels_have_gaps(self):
        with_gaps = {mmsi for mmsi, a in self.assessed.items() if a.has_gap}
        self.assertEqual(with_gaps, {V002, V003})



class TestGapRelevanceEdgeCases(unittest.TestCase):
    """Relevance requires window overlap AND a nearby endpoint - neither alone suffices."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = load_case_inputs()
        cls.origin = estimate_origin(cls.inputs["slickRing"], cls.inputs["observedAt"],
                                     cls.inputs["window"], cls.inputs["field"])
        cls.window = cls.inputs["window"]

    def judge(self, records, config=None):
        trajectory = trajectory_from_records(records).by_mmsi()[records[0]["mmsi"]]
        assessment = analyse_gaps(trajectory, self.origin, self.window, config)
        self.assertEqual(len(assessment.gaps), 1, "fixture must produce exactly one gap")
        return assessment

    def reason_text(self, assessment) -> str:
        return " ".join(assessment.gaps[0].reasons)

    def test_gap_before_the_window_is_not_relevant(self):
        """Inside the region, but hours before the oil was released."""
        start = iso(secs(WINDOW_START) - 5 * 3600)
        records = gapped_track("111111111", RELEASE_LAT, RELEASE_LON, start,
                               gap_hours=2.0)
        assessment = self.judge(records)
        fact = assessment.gaps[0]
        self.assertFalse(fact.overlaps_window)
        self.assertEqual(fact.relevance, 0.0)
        self.assertFalse(assessment.any_relevant)
        self.assertIn("does not overlap the release window - not relevant",
                      self.reason_text(assessment))

    def test_gap_between_distant_endpoints_is_not_relevant(self):
        """Inside the window, but both ends are 100 km from the region."""
        lat, lon = offset_position(RELEASE_LAT, RELEASE_LON, 90.0, 100.0)
        records = gapped_track("222222222", lat, lon, WINDOW_START, gap_hours=2.0)
        assessment = self.judge(records)
        fact = assessment.gaps[0]
        self.assertTrue(fact.overlaps_window)
        self.assertFalse(fact.endpoint_near_region)
        self.assertEqual(fact.relevance, 0.0)
        self.assertIn("both endpoints are further than 30 km from the origin region",
                      self.reason_text(assessment))

    def test_gap_with_an_endpoint_only_near_the_region_earns_half_relevance(self):
        """A 20 km approach is worth half of a genuine entry - reported, not rounded away."""
        lat, lon = offset_position(RELEASE_LAT, RELEASE_LON, 90.0, 20.0)
        records = gapped_track("333333333", lat, lon, WINDOW_START, gap_hours=2.0)
        assessment = self.judge(records)
        fact = assessment.gaps[0]
        self.assertTrue(fact.endpoint_near_region)
        self.assertFalse(fact.before["insideRegion"])
        self.assertEqual(fact.relevance, 0.5)
        self.assertIn("near the origin region - relevant", self.reason_text(assessment))

    def test_a_station_keeping_vessel_has_a_trivially_feasible_gap(self):
        """Zero distance to bridge: relevance 1.0 and feasible, but the engine's cap
        still limits what a gap may contribute (tested in test_scoring_engine.py)."""
        records = gapped_track("444444444", RELEASE_LAT, RELEASE_LON, WINDOW_START,
                               gap_hours=0.6)
        assessment = self.judge(records)
        fact = assessment.gaps[0]
        self.assertGreater(fact.relevance, 0.0)
        self.assertIs(fact.feasible, True)
        self.assertGreater(assessment.best_evidence_value, 0.0)

    def test_a_genuinely_impossible_bridge_earns_no_evidence(self):
        """200 km bridged in one hour is ~108 kn: relevance cannot rescue it."""
        mmsi = "666666666"
        start = secs(WINDOW_START)
        before = [rec(mmsi, iso(start + k * 300), RELEASE_LAT, RELEASE_LON)
                  for k in range(6)]
        far_lat, far_lon = offset_position(RELEASE_LAT, RELEASE_LON, 90.0, 200.0)
        resume = start + 5 * 300 + 3600
        after = [rec(mmsi, iso(resume + k * 300), round(far_lat, 6), round(far_lon, 6))
                 for k in range(6)]
        assessment = self.judge(before + after)
        fact = assessment.gaps[0]
        self.assertEqual(fact.relevance, 1.0)
        self.assertIs(fact.feasible, False)
        self.assertGreater(fact.implied_speed_kn, fact.cap_speed_kn)
        self.assertEqual(assessment.best_evidence_value, 0.0)
        self.assertIn("INFEASIBLE", self.reason_text(assessment))

    def test_invalid_configuration_is_rejected(self):
        for kwargs in ({"feasibility_margin": 0.9}, {"min_feasible_speed_kn": 0.0},
                       {"global_max_speed_kn": 0.0}, {"endpoint_near_region_km": 0.0}):
            with self.assertRaises(ValueError, msg=f"config {kwargs} must be rejected"):
                GapAnalysisConfig(**kwargs)

    def test_config_describes_every_threshold_it_owns(self):
        described = GapAnalysisConfig().describe()
        for key in ("feasibilityMargin", "minFeasibleSpeedKn", "globalMaxSpeedKn",
                    "endpointNearRegionKm"):
            self.assertIn(key, described)

    def test_deterministic_and_json_serialisable(self):
        records = gapped_track("555555555", RELEASE_LAT, RELEASE_LON, WINDOW_START,
                               gap_hours=2.0)
        first = self.judge(records)
        second = self.judge(records)
        self.assertEqual(json.dumps(first.to_dict(), sort_keys=True),
                         json.dumps(second.to_dict(), sort_keys=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)

