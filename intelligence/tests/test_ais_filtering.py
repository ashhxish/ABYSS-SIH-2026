#!/usr/bin/env python3
"""ABYSS - Phase 5-7 tests for spatial, temporal and trajectory compatibility.

WHAT THESE TESTS PROVE
    1. the compatibility filter separates the vessels the scenario designed to be
       separable: EXACTLY three vessels (V001, V002, V003) are inside the reconstructed
       origin region while the release window is open, and that set matches the
       generator's declared presence set in the answer key
    2. the SAME coordinates mean different things at different times. V004 is 13 km from
       the region at some point in its track but 119 km away DURING the window, and V012
       passes straight through the region only after the window closed. Both fail the
       temporal filter even though their whole-track proximity looks impressive - the
       isolation of test cases B and G
    3. distances are geodesic and measured to the ESTIMATED region: a position inside the
       region is 0.0 km by definition, and no vessel's whole-track minimum can exceed its
       in-window minimum
    4. the three filters are independent annotations on top of the facts: passing spatial
       proximity alone does not pass the temporal gate, and no field here carries a score,
       suspicion or rank
    5. the trajectory filter measures the physical plausibility of observed motion inside
       the window against a per-vessel speed cap, and reports a warning instead of
       inventing a fraction when there is no in-window movement at all
    6. crafted edge cases behave: a vessel moored on the release point, a vessel 10 km
       outside it, a track that ends before the window opens, and invalid configuration

WHAT THESE TESTS DO NOT DO
    No behaviour comparison, no gap relevance, no evidence scoring, no ranking. Pass/fail
    flags are checked as annotations, never as conclusions.

RUN (needs the project virtual environment)
    .venv/bin/python -m unittest discover -s intelligence/tests -v
    .venv/bin/python intelligence/tests/test_ais_filtering.py -v
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
from app.ais.filtering import (CompatibilityConfig, CompatibilityError, assess_compatibility)
from app.ais.trajectory import build_trajectories_from_cleaning, trajectory_from_records
from app.geo import distance_to_ring_km, offset_position
from app.hindcast.origin import estimate_origin
from app.investigation import load_case_inputs

UTC = timezone.utc
T0 = datetime(2026, 3, 11, 6, 0, 0, tzinfo=UTC)

# Vessel identities are fixed by the committed CASE-001 bundle.
V001, V002, V003 = "900000001", "900000002", "900000003"
V004, V005, V006 = "900000004", "900000005", "900000006"
V007, V008, V009 = "900000007", "900000008", "900000009"
V010, V011, V012 = "900000010", "900000011", "900000012"

INSIDE_DURING_WINDOW = {V001, V002, V003}
FALLOFF_KM = 30.0
RELEASE_LAT, RELEASE_LON = 18.3, 71.9     # answer-key coordinate, used only for fixtures
WINDOW_START = "2026-03-13T10:00:00Z"
WINDOW_END = "2026-03-13T18:00:00Z"


def iso(seconds: int) -> str:
    """ISO-8601 UTC timestamp `seconds` after T0 (2026-03-11T06:00:00Z)."""
    return (T0 + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def rec(mmsi: str, timestamp: str, lat: float, lon: float,
        sog: float = 8.0, cog: float = 45.0) -> dict:
    """One crafted AIS record for the edge-case fixtures."""
    return {"mmsi": mmsi, "timestamp": timestamp, "latitude": lat, "longitude": lon,
            "sogKn": sog, "cogDeg": cog, "vesselName": f"TEST {mmsi}",
            "datasetLabel": "Synthetic Demonstration Dataset", "synthetic": True}


def moored_track(mmsi: str, lat: float, lon: float, start_iso: str,
                 steps: int = 20, interval_s: int = 300) -> list:
    """A stationary track - the 'in the region but not moving' edge case."""
    start = int((datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                 - T0).total_seconds())
    return [rec(mmsi, iso(start + k * interval_s), lat, lon, sog=0.2)
            for k in range(steps)]


def slow_drift_track(mmsi: str, lat: float, lon: float, start_iso: str,
                     steps: int = 20, interval_s: int = 300,
                     bearing: float = 45.0, speed_kn: float = 6.0) -> list:
    """A short leg of real, self-consistent travel from a chosen position."""
    start = int((datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                 - T0).total_seconds())
    km_per_step = speed_kn * 1.852 * (interval_s / 3600.0)
    rows, cur_lat, cur_lon = [], lat, lon
    for k in range(steps):
        rows.append(rec(mmsi, iso(start + k * interval_s), round(cur_lat, 6),
                        round(cur_lon, 6), sog=speed_kn, cog=bearing))
        cur_lat, cur_lon = offset_position(cur_lat, cur_lon, bearing, km_per_step)
    return rows


class TestDemoCompatibility(unittest.TestCase):
    """What the three filters say about the twelve designed vessels."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = load_case_inputs()
        cls.origin = estimate_origin(cls.inputs["slickRing"], cls.inputs["observedAt"],
                                     cls.inputs["window"], cls.inputs["field"])
        cls.window = cls.inputs["window"]
        cleaned = clean_demo_case()
        cls.trajectories = build_trajectories_from_cleaning(cleaned).by_mmsi()
        cls.assessed = {
            mmsi: assess_compatibility(trajectory, cls.origin, cls.window)
            for mmsi, trajectory in cls.trajectories.items()
        }

    def a(self, mmsi: str):
        return self.assessed[mmsi]

    # --- spatial / temporal separation (specification cases A, B, C, G) ------
    def test_exactly_the_designed_three_vessels_are_inside_during_the_window(self):
        inside = {mmsi for mmsi, a in self.assessed.items()
                  if a.inside_region_during_window}
        self.assertEqual(inside, INSIDE_DURING_WINDOW)

    def test_the_presence_set_matches_the_generators_declared_intent(self):
        """The answer key states the intent; the reconstruction must reproduce it."""
        key_path = (INTELLIGENCE_DIR / "data" / "demo" / "case_001"
                    / "demo_origin_expected.json")
        key = json.loads(key_path.read_text(encoding="utf-8"))
        declared = {row["mmsi"] for row in key["vesselSummaries"]
                    if row["expected"]["inOriginRegionDuringWindow"]}
        self.assertEqual(declared, INSIDE_DURING_WINDOW)
        measured = {mmsi for mmsi, a in self.assessed.items()
                    if a.inside_region_during_window}
        self.assertEqual(measured, declared)

    def test_inside_the_region_means_zero_kilometres_by_definition(self):
        for mmsi in INSIDE_DURING_WINDOW:
            assessment = self.a(mmsi)
            self.assertEqual(assessment.min_distance_km_during_window, 0.0, mmsi)
            self.assertEqual(assessment.inside_region_relation, "during_window", mmsi)
            self.assertTrue(assessment.spatial_pass, mmsi)
            self.assertTrue(assessment.temporal_pass, mmsi)
            self.assertGreater(assessment.window_presence_seconds, 0, mmsi)

    def test_nearest_vessel_to_the_slick_is_far_from_the_origin_during_the_window(self):
        """Case G: the slick-proximity trap. V004 is close to the oil, not the origin."""
        assessment = self.a(V004)
        self.assertFalse(assessment.inside_region_during_window)
        self.assertFalse(assessment.inside_region_anytime)
        self.assertEqual(assessment.inside_region_relation, "never")
        self.assertGreater(assessment.min_distance_km_during_window, FALLOFF_KM)
        self.assertLess(assessment.min_distance_km_whole_track, FALLOFF_KM)
        self.assertFalse(assessment.spatial_pass)
        self.assertFalse(assessment.temporal_pass)

    def test_wrong_time_candidate_crosses_the_region_after_the_window_closes(self):
        """Case B: right place, wrong time - caught by the temporal filter alone."""
        for mmsi in (V005, V012):
            assessment = self.a(mmsi)
            self.assertTrue(assessment.inside_region_anytime, mmsi)
            self.assertFalse(assessment.inside_region_during_window, mmsi)
            self.assertEqual(assessment.inside_region_relation, "after_window", mmsi)
            self.assertFalse(assessment.temporal_pass, mmsi)
            self.assertEqual(assessment.window_presence_seconds, 0, mmsi)

    def test_anomalous_but_remote_vessel_is_never_present(self):
        """Case F: V006's behaviour is another phase's problem; location fails here."""
        assessment = self.a(V006)
        self.assertEqual(assessment.inside_region_relation, "never")
        self.assertGreater(assessment.min_distance_km_during_window, 150.0)
        self.assertFalse(assessment.spatial_pass)


    # --- measurement discipline ---------------------------------------------
    def test_whole_track_minimum_can_never_beat_the_in_window_minimum(self):
        for mmsi, assessment in self.assessed.items():
            if assessment.min_distance_km_during_window is None:
                continue
            self.assertLessEqual(assessment.min_distance_km_whole_track,
                                 assessment.min_distance_km_during_window + 1e-6, mmsi)

    def test_distances_are_geodesic_to_the_region_ring(self):
        """Recompute one vessel's whole-track minimum independently of the module."""
        trajectory = self.trajectories[V007]
        expected = min(distance_to_ring_km(p.latitude, p.longitude, self.origin.region_ring)
                       for p in trajectory.points)
        self.assertAlmostEqual(self.a(V007).min_distance_km_whole_track, expected, places=3)

    def test_being_outside_the_falloff_is_not_presence(self):
        """V010 approaches to ~53 km during the window: outside the falloff, not present."""
        assessment = self.a(V010)
        self.assertFalse(assessment.spatial_pass)
        self.assertFalse(assessment.inside_region_during_window)
        self.assertGreater(assessment.min_distance_km_during_window, FALLOFF_KM)

    # --- trajectory plausibility (Phase 7) ----------------------------------
    def test_observed_motion_inside_the_window_is_physically_plausible(self):
        for mmsi in INSIDE_DURING_WINDOW:
            assessment = self.a(mmsi)
            self.assertGreater(assessment.segments_in_window, 0, mmsi)
            self.assertEqual(assessment.plausible_segment_fraction, 1.0, mmsi)
            self.assertTrue(assessment.trajectory_pass, mmsi)
            self.assertTrue(assessment.movement_through_region, mmsi)

    def test_speed_cap_is_derived_per_vessel_and_bounded(self):
        for mmsi, assessment in self.assessed.items():
            own_max = self.trajectories[mmsi].stats.get("maxReportedSogKn")
            self.assertLessEqual(assessment.speed_cap_kn, 60.0, mmsi)
            self.assertGreaterEqual(assessment.speed_cap_kn, 5.0, mmsi)
            if own_max:
                self.assertGreaterEqual(assessment.speed_cap_kn, own_max, mmsi)

    def test_filters_are_annotations_and_carry_no_scoring_fields(self):
        for mmsi, assessment in self.assessed.items():
            payload = json.dumps(assessment.to_dict()).lower()
            for forbidden in ("suspicion", "score", "guilt"):
                self.assertNotIn(forbidden, payload, f"{mmsi} leaked {forbidden}")
            self.assertIn("pass/fail flags annotate the facts",
                          " ".join(assessment.notes))



class TestCompatibilityEdgeCases(unittest.TestCase):
    """Crafted tracks: the filters must behave on inputs the bundle does not contain."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = load_case_inputs()
        cls.origin = estimate_origin(cls.inputs["slickRing"], cls.inputs["observedAt"],
                                     cls.inputs["window"], cls.inputs["field"])
        cls.window = cls.inputs["window"]

    def assess(self, records, config=None):
        trajectory = trajectory_from_records(records).by_mmsi()[records[0]["mmsi"]]
        return assess_compatibility(trajectory, self.origin, self.window, config)

    def test_a_vessel_sitting_on_the_release_point_is_inside_during_the_window(self):
        records = moored_track("111111111", RELEASE_LAT, RELEASE_LON, WINDOW_START)
        assessment = self.assess(records)
        self.assertTrue(assessment.inside_region_during_window)
        self.assertEqual(assessment.inside_region_relation, "during_window")
        self.assertEqual(assessment.min_distance_km_during_window, 0.0)
        self.assertTrue(assessment.temporal_pass)

    def test_a_vessel_ten_km_outside_is_near_but_not_present(self):
        lat, lon = offset_position(RELEASE_LAT, RELEASE_LON, 90.0, 10.0)
        records = slow_drift_track("222222222", lat, lon, WINDOW_START)
        assessment = self.assess(records)
        self.assertFalse(assessment.inside_region_during_window)
        self.assertLessEqual(assessment.min_distance_km_during_window, FALLOFF_KM)
        self.assertTrue(assessment.spatial_pass,
                        "within the falloff must pass the spatial annotation")
        self.assertFalse(assessment.temporal_pass, "proximity is not presence")

    def test_a_track_that_ends_before_the_window_opens_is_reported_not_guessed(self):
        records = slow_drift_track("333333333", RELEASE_LAT, RELEASE_LON,
                                   "2026-03-13T00:00:00Z")
        assessment = self.assess(records)
        self.assertIsNone(assessment.min_distance_km_during_window)
        self.assertEqual(assessment.records_in_window, 0)
        self.assertEqual(assessment.segments_in_window, 0)
        self.assertEqual(assessment.plausible_segment_fraction, 0.0)
        self.assertFalse(assessment.trajectory_pass)
        self.assertIn("no observed segments start inside the release window",
                      assessment.warnings)

    def test_invalid_configuration_is_rejected(self):
        for kwargs in ({"spatial_falloff_km": 0.0},
                       {"trajectory_plausibility_floor": 1.5},
                       {"max_plausible_speed_kn": 0.0},
                       {"speed_safety_factor": 0.5},
                       {"min_speed_cap_kn": 0.0}):
            with self.assertRaises(ValueError, msg=f"config {kwargs} must be rejected"):
                CompatibilityConfig(**kwargs)

    def test_config_describes_every_threshold_it_owns(self):
        described = CompatibilityConfig().describe()
        for key in ("spatialFalloffKm", "trajectoryPlausibilityFloor",
                    "maxPlausibleSpeedKn", "speedSafetyFactor", "minSpeedCapKn"):
            self.assertIn(key, described)

    def test_assessment_is_json_serialisable(self):
        records = moored_track("444444444", RELEASE_LAT, RELEASE_LON, WINDOW_START)
        payload = self.assess(records).to_dict()
        self.assertEqual(payload["mmsi"], "444444444")
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)

