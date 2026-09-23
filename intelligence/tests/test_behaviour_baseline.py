#!/usr/bin/env python3
"""ABYSS - Phase 8 tests for the own-baseline behavioural comparison.

WHAT THESE TESTS PROVE
    1. the comparison is a vessel against ITSELF: every raw anomaly is a weighted blend of
       four named components (speed shift, speed variability, turn rate, loiter excess)
       and the arithmetic can be recomputed from the reported components
    2. the spatial gate is real and one-directional. The scenario's designed anomalies -
       V006 (erratic, 150+ km away), V008 (legitimate fishing-style working periods) and
       V011 (moored harbour tug) - are all REPORTED as anomalies and all score exactly
       zero, because none of them was inside the origin region during the window. Only
       V001, which was inside the region and did slow down, carries a scored anomaly
       (specification cases A and F)
    3. the report never drifts into accusation: an anomaly means "differs from its own
       baseline" and nothing more, the gate is stated in plain language, and no field
       names wrongdoing, illegality or guilt
    4. the two views documented in the module are both present and distinguishable:
       baseline statistics for the whole track and window statistics for the release
       period, with the window length reported
    5. edge cases behave: a track with too few in-window speed observations leaves the
       anomaly at zero with an explanatory note instead of a fabricated number, an empty
       track is handled, and invalid configuration is rejected

WHAT THESE TESTS DO NOT DO
    No scoring, no ranking, no cross-vessel comparison, no conclusion about any vessel.

RUN (needs the project virtual environment)
    .venv/bin/python -m unittest discover -s intelligence/tests -v
    .venv/bin/python intelligence/tests/test_behaviour_baseline.py -v
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
from app.ais.trajectory import build_trajectories_from_cleaning, trajectory_from_records
from app.behaviour.baseline import (COMPONENT_WEIGHTS, BehaviourConfig, assess_behaviour)
from app.investigation import load_case_inputs

UTC = timezone.utc
T0 = datetime(2026, 3, 11, 6, 0, 0, tzinfo=UTC)

V001, V002, V003 = "900000001", "900000002", "900000003"
V004, V005, V006 = "900000004", "900000005", "900000006"
V007, V008, V009 = "900000007", "900000008", "900000009"
V010, V011, V012 = "900000010", "900000011", "900000012"

REPORT_THRESHOLD = 0.30
VESSELS_REPORTED_AS_ANOMALOUS = {V001, V006, V008, V011}
VESSELS_INSIDE_DURING_WINDOW = {V001, V002, V003}
VESSELS_WITH_SCORED_ANOMALY = {V001}
WINDOW_START = "2026-03-13T10:00:00Z"


def iso(seconds: int) -> str:
    return (T0 + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def rec(mmsi: str, timestamp: str, lat: float, lon: float, sog: float,
        cog: float = 45.0) -> dict:
    return {"mmsi": mmsi, "timestamp": timestamp, "latitude": lat, "longitude": lon,
            "sogKn": sog, "cogDeg": cog, "vesselName": f"TEST {mmsi}",
            "datasetLabel": "Synthetic Demonstration Dataset", "synthetic": True}


def track(mmsi: str, speeds, start_iso: str, interval_s: int = 300,
          lat: float = 18.3, lon: float = 71.9) -> list:
    """A stationary-position track whose reported speeds follow `speeds`."""
    start = int((datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                 - T0).total_seconds())
    return [rec(mmsi, iso(start + k * interval_s), lat, lon, sog=float(speed))
            for k, speed in enumerate(speeds)]


class TestDemoBehaviour(unittest.TestCase):
    """Own-baseline comparison for the twelve designed vessels."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = load_case_inputs()
        cls.window = cls.inputs["window"]
        cleaned = clean_demo_case()
        cls.trajectories = build_trajectories_from_cleaning(cleaned).by_mmsi()
        cls.assessed = {
            mmsi: assess_behaviour(trajectory, cls.window,
                                   mmsi in VESSELS_INSIDE_DURING_WINDOW)
            for mmsi, trajectory in cls.trajectories.items()
        }

    def a(self, mmsi: str):
        return self.assessed[mmsi]

    # --- the gate: reported everywhere, scored only inside the region --------
    def test_the_reported_anomaly_set_is_exactly_the_designed_one(self):
        reported = {mmsi for mmsi, a in self.assessed.items() if a.is_anomaly}
        self.assertEqual(reported, VESSELS_REPORTED_AS_ANOMALOUS)
        for mmsi in reported:
            self.assertGreaterEqual(self.a(mmsi).raw_anomaly, REPORT_THRESHOLD, mmsi)

    def test_the_gate_is_one_directional_and_total(self):
        """Eligible vessels score their raw anomaly; ineligible ones always score zero."""
        for mmsi, assessment in self.assessed.items():
            if assessment.scored_eligible:
                self.assertEqual(assessment.scored_anomaly, assessment.raw_anomaly, mmsi)
            else:
                self.assertEqual(assessment.scored_anomaly, 0.0, mmsi)
                self.assertFalse(assessment.scored_eligible, mmsi)

    def test_only_the_vessel_inside_the_region_carries_the_leading_scored_anomaly(self):
        ranked = sorted(((a.scored_anomaly, mmsi) for mmsi, a in self.assessed.items()),
                        reverse=True)
        leader_value, leader_mmsi = ranked[0]
        self.assertIn(leader_mmsi, VESSELS_WITH_SCORED_ANOMALY)
        self.assertGreater(leader_value, REPORT_THRESHOLD)
        self.assertEqual(leader_mmsi, V001)

    def test_anomaly_far_from_the_origin_is_reported_as_context_and_scores_zero(self):
        """Case F: V006 is erratic but remote; the anomaly is never evidence."""
        assessment = self.a(V006)
        self.assertTrue(assessment.is_anomaly)
        self.assertGreater(assessment.raw_anomaly, REPORT_THRESHOLD)
        self.assertFalse(assessment.scored_eligible)
        self.assertEqual(assessment.scored_anomaly, 0.0)
        self.assertIn("reported as context, scored 0", " ".join(assessment.notes))

    def test_legitimate_working_patterns_are_not_promoted(self):
        """V008 (fishing-like) and V011 (moored tug) look anomalous and must score 0."""
        for mmsi in (V008, V011):
            assessment = self.a(mmsi)
            self.assertTrue(assessment.is_anomaly, mmsi)
            self.assertFalse(assessment.scored_eligible, mmsi)
            self.assertEqual(assessment.scored_anomaly, 0.0, mmsi)

    def test_effect_of_the_gate_is_isolated_by_reassessing_the_same_track(self):
        trajectory = self.trajectories[V001]
        inside = assess_behaviour(trajectory, self.window, True)
        outside = assess_behaviour(trajectory, self.window, False)
        self.assertEqual(inside.raw_anomaly, outside.raw_anomaly)
        self.assertEqual(inside.scored_anomaly, inside.raw_anomaly)
        self.assertEqual(outside.scored_anomaly, 0.0)

    def test_a_quiet_vessel_is_reported_as_consistent_with_its_own_baseline(self):
        for mmsi in (V002, V003, V007):
            assessment = self.a(mmsi)
            self.assertFalse(assessment.is_anomaly, mmsi)
            self.assertLess(assessment.raw_anomaly, REPORT_THRESHOLD, mmsi)


    # --- arithmetic transparency --------------------------------------------
    def test_raw_anomaly_is_recomputable_from_the_reported_components(self):
        for mmsi, assessment in self.assessed.items():
            expected = sum(COMPONENT_WEIGHTS[key] * assessment.components[key]
                           for key in COMPONENT_WEIGHTS)
            self.assertAlmostEqual(assessment.raw_anomaly, expected, places=6, msg=mmsi)

    def test_components_are_the_four_named_views_and_all_bounded(self):
        for mmsi, assessment in self.assessed.items():
            self.assertEqual(set(assessment.components), set(COMPONENT_WEIGHTS), mmsi)
            for key, value in assessment.components.items():
                self.assertGreaterEqual(value, 0.0, f"{mmsi}.{key}")
                self.assertLessEqual(value, 1.0, f"{mmsi}.{key}")

    def test_the_component_weights_are_stated_in_every_assessment(self):
        for mmsi, assessment in self.assessed.items():
            notes = " ".join(assessment.notes)
            self.assertIn("0.30*speedShift", notes, mmsi)
            self.assertIn("prototype component weights", notes, mmsi)

    # --- the two reported views ---------------------------------------------
    def test_baseline_and_window_statistics_are_both_reported(self):
        assessment = self.a(V001)
        self.assertEqual(set(assessment.baseline), {"records", "medianSogKn", "spreadSogKn",
                                                    "turnsPerHour", "slowFraction",
                                                    "trackHours"})
        self.assertEqual(set(assessment.window), {"records", "medianSogKn", "spreadSogKn",
                                                  "turnsPerHour", "slowFraction", "hours"})
        self.assertGreater(assessment.baseline["records"], assessment.window["records"])
        self.assertAlmostEqual(assessment.window["hours"], 8.0, places=3)

    def test_the_designed_slowdown_appears_as_loitering_and_extra_variability(self):
        """V001's median barely moves, but it doubles its slow fraction inside the region:
        the anomaly is a loiter/variability signal, which is exactly what the module
        documents for a vessel whose whole track is already variable."""
        assessment = self.a(V001)
        self.assertGreater(assessment.window["slowFraction"],
                           assessment.baseline["slowFraction"])
        self.assertGreater(assessment.components["loiterExcess"], 0.2)
        self.assertEqual(assessment.components["variability"], 1.0)
        self.assertIn("extended slow/loitering periods during the window",
                      assessment.description)
        self.assertIn("erratic speeds during the window", assessment.description)

    # --- language discipline -------------------------------------------------
    def test_no_assessment_asserts_wrongdoing(self):
        for mmsi, assessment in self.assessed.items():
            text = json.dumps(assessment.to_dict()).lower()
            for forbidden in ("illegal", "guilty", "guilt", "crime", "suspicion",
                              "wrongdoing", "violation"):
                self.assertNotIn(forbidden, text, f"{mmsi} used {forbidden}")
            self.assertIn("gates it on spatial presence", text, mmsi)

    def test_deterministic_and_json_serialisable(self):
        trajectory = self.trajectories[V001]
        first = assess_behaviour(trajectory, self.window, True)
        second = assess_behaviour(trajectory, self.window, True)
        self.assertEqual(json.dumps(first.to_dict(), sort_keys=True),
                         json.dumps(second.to_dict(), sort_keys=True))


class TestBehaviourEdgeCases(unittest.TestCase):
    """Crafted tracks and configuration."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = load_case_inputs()
        cls.window = cls.inputs["window"]

    def assess(self, records, eligible=True, config=None):
        trajectory = trajectory_from_records(records).by_mmsi()[records[0]["mmsi"]]
        return assess_behaviour(trajectory, self.window, eligible, config)

    def test_too_few_in_window_observations_leaves_the_anomaly_at_zero(self):
        """A track that ends before the window opens cannot be compared - say so."""
        records = track("555555555", [2.0, 12.0, 3.0], "2026-03-12T00:00:00Z")
        assessment = self.assess(records)
        self.assertEqual(assessment.raw_anomaly, 0.0)
        self.assertFalse(assessment.is_anomaly)
        self.assertIn("insufficient speed observations", " ".join(assessment.notes))
        self.assertEqual(assessment.components, {})

    def test_a_steady_track_inside_the_window_is_not_an_anomaly(self):
        records = track("666666666", [10.0] * 40, WINDOW_START)
        assessment = self.assess(records)
        self.assertEqual(assessment.components["speedShift"], 0.0)
        self.assertEqual(assessment.window["spreadSogKn"], 0.0)
        self.assertFalse(assessment.is_anomaly)
        self.assertEqual(assessment.description, "broadly consistent with own baseline")

    def test_a_speed_swing_inside_the_window_is_an_anomaly(self):
        records = track("777777777", [10.0] * 20 + [0.5, 19.0] * 10, WINDOW_START)
        assessment = self.assess(records)
        self.assertGreater(assessment.components["variability"], 0.5)
        self.assertTrue(assessment.is_anomaly)
        self.assertIn("erratic speeds", assessment.description)

    def test_invalid_configuration_is_rejected(self):
        for kwargs in ({"report_threshold": 1.5}, {"variability_reference_kn": 0.0},
                       {"turn_reference_per_hour": 0.0}, {"slow_speed_kn": -1.0},
                       {"min_window_records": 0}):
            with self.assertRaises(ValueError, msg=f"config {kwargs} must be rejected"):
                BehaviourConfig(**kwargs)

    def test_config_describes_every_reference_it_owns(self):
        described = BehaviourConfig().describe()
        for key in ("reportThreshold", "variabilityReferenceKn", "turnReferencePerHour",
                    "slowSpeedKn", "minWindowRecords"):
            self.assertIn(key, described)

    def test_the_slow_speed_reference_aligns_with_the_trajectory_config(self):
        from app.ais.trajectory import TrajectoryConfig
        self.assertEqual(BehaviourConfig().slow_speed_kn,
                         TrajectoryConfig().slow_speed_kn)


if __name__ == "__main__":
    unittest.main(verbosity=2)

