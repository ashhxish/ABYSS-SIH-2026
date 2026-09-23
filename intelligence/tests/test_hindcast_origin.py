#!/usr/bin/env python3
"""ABYSS - Phase 11 tests for the backward-drift origin reconstruction.

WHAT THESE TESTS PROVE
    1. the hindcast reproduces the scenario it was designed for: the reconstructed
       REGION contains the generator's true release point - an answer-key coordinate the
       pipeline itself never reads - while the observed slick centroid, ~33 km
       downstream, lies OUTSIDE it. "The slick is not the release location" is therefore a
       measured property of the model, not a claim in a document
    2. the result is a REGION with uncertainty, never a point estimate: a polygon with
       area, bounds, spread and a confidence in (0, 1], and no point-estimate field
    3. the candidate release window travels with the estimate, keeps its provenance, and
       reports how old its boundaries are relative to the observation (20 h / 12 h)
    4. every parameter is reported as a prototype value (integration step, windage,
       positional buffer, sampling stride) - none is presented as a calibrated constant
    5. the environmental field is a real interpolator: lookup at a grid node reproduces
       that node exactly, drift equals current + windage x wind, out-of-grid input is
       clamped rather than fatal, a missing file fails loudly, and a structurally broken
       field (declared 2x2 grid, zero nodes) is rejected instead of zero-filled
    6. hindcasting is deterministic - two runs produce identical JSON - and degenerate
       input fails loudly instead of collapsing into an implicit point estimate

WHAT THESE TESTS DO NOT DO
    No AIS filtering, no behaviour comparison, no gap analysis, no scoring, no ranking.
    They never feed the answer key into the pipeline either: demo_origin_expected.json is
    read here ONLY as a fixture, which is exactly what investigation.py's contract says
    the answer keys are for.

RUN (needs the project virtual environment)
    .venv/bin/python -m unittest discover -s intelligence/tests -v
    .venv/bin/python intelligence/tests/test_hindcast_origin.py -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

INTELLIGENCE_DIR = Path(__file__).resolve().parent.parent
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from app.geo import haversine_km
from app.hindcast.environmental import EnvironmentalField, EnvironmentalFieldError
from app.hindcast.origin import (OriginConfig, OriginHindcastError, estimate_origin)
from app.investigation import load_case_inputs
from app.timeutils import ReleaseWindow, epoch_seconds

# ---------------------------------------------------------------------------
# Scenario constants. They come from the committed CASE-001 bundle and are repeated
# here on purpose: a regeneration that moves the release point must fail this module.
# ---------------------------------------------------------------------------
RELEASE_LAT = 18.3
RELEASE_LON = 71.9
SLICK_CENTROID = (18.466325, 72.163105)
WINDOW_START = "2026-03-13T10:00:00Z"
WINDOW_END = "2026-03-13T18:00:00Z"
OBSERVED_AT = "2026-03-14T06:00:00Z"
WINDOW_HOURS = 8.0
HOURS_BEFORE_OBSERVATION = {"start": 20.0, "end": 12.0}
FIELD_WINDAGE = 0.03


def load_answer_key() -> dict:
    """The scenario answer key - a TEST FIXTURE, never a pipeline input."""
    path = (INTELLIGENCE_DIR / "data" / "demo" / "case_001"
            / "demo_origin_expected.json")
    return json.loads(path.read_text(encoding="utf-8"))



class TestDemoOriginReconstruction(unittest.TestCase):
    """The CASE-001 hindcast: what the product reconstructs, and how honestly."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = load_case_inputs()
        cls.origin = estimate_origin(cls.inputs["slickRing"], cls.inputs["observedAt"],
                                     cls.inputs["window"], cls.inputs["field"])
        cls.payload = cls.origin.to_dict()
        cls.answer_key = load_answer_key()

    # --- the region is a region, not a point --------------------------------
    def test_region_is_a_closed_polygon_with_positive_area(self):
        ring = self.origin.region_ring
        self.assertGreaterEqual(len(ring), 3)
        self.assertEqual(ring[0], ring[-1], "the region ring must be closed")
        self.assertGreater(self.origin.area_km2, 0.0)
        bounds = self.origin.bounds
        self.assertLess(bounds["minLat"], bounds["maxLat"])
        self.assertLess(bounds["minLon"], bounds["maxLon"])

    def test_no_point_estimate_is_published_anywhere(self):
        """A single coordinate would overstate what the model can know."""
        region = self.payload["region"]
        self.assertNotIn("centroid", region)
        self.assertNotIn("point", region)
        self.assertNotIn("releasePoint", region)
        self.assertEqual(region["geometry"]["type"], "Polygon")
        self.assertIn("never a single point", " ".join(region["notes"]))

    def test_confidence_and_spread_are_reported_and_inside_their_range(self):
        self.assertGreater(self.origin.confidence, 0.0)
        self.assertLessEqual(self.origin.confidence, 1.0)
        self.assertGreater(self.origin.spread_km, 0.0)
        self.assertEqual(self.payload["region"]["confidence"],
                         round(self.origin.confidence, 3))

    # --- the reconstruction actually lands on the designed origin -----------
    def test_region_contains_the_true_release_point_from_the_answer_key(self):
        """The strongest available check that the hindcast is not decorative."""
        key = self.answer_key["trueReleasePoint"]
        self.assertTrue(
            self.origin.region_contains(key["lat"], key["lon"]),
            f"the reconstructed region must contain the designed release point {key}")
        self.assertEqual(self.origin.distance_to_region_km(key["lat"], key["lon"]), 0.0)

    def test_region_centroid_sits_within_a_few_km_of_the_release_point(self):
        ring = self.origin.region_ring
        centroid_lat = sum(p[1] for p in ring) / len(ring)
        centroid_lon = sum(p[0] for p in ring) / len(ring)
        offset = haversine_km(centroid_lat, centroid_lon, RELEASE_LAT, RELEASE_LON)
        self.assertLess(offset, 5.0,
                        f"region centroid is {offset:.2f} km from the designed "
                        "release point")

    def test_observed_slick_centroid_is_outside_the_region(self):
        """The teaching point: oil drifts, so the slick is NOT the release site."""
        distance = self.origin.distance_to_region_km(*SLICK_CENTROID)
        self.assertFalse(self.origin.region_contains(*SLICK_CENTROID))
        self.assertGreater(distance, 10.0)
        self.assertEqual(self.answer_key["observedVsRelease"]["observedSlickCentroid"],
                         {"lat": SLICK_CENTROID[0], "lon": SLICK_CENTROID[1]})

    def test_backdrift_path_starts_at_the_slick_and_ends_at_the_origin(self):
        path = self.origin.backdrift_path          # [(lat, lon), ...]
        self.assertGreaterEqual(len(path), 2)
        self.assertAlmostEqual(path[0][0], SLICK_CENTROID[0], places=3)
        self.assertAlmostEqual(path[0][1], SLICK_CENTROID[1], places=3)
        drifted_km = haversine_km(path[0][0], path[0][1], path[-1][0], path[-1][1])
        self.assertGreater(drifted_km, 10.0)
        self.assertLess(haversine_km(path[-1][0], path[-1][1], RELEASE_LAT, RELEASE_LON),
                        10.0)

    # --- the window travels with the estimate -------------------------------
    def test_release_window_is_carried_through_with_provenance(self):
        window = self.payload["releaseWindow"]
        self.assertEqual(window["start"], WINDOW_START)
        self.assertEqual(window["end"], WINDOW_END)
        self.assertAlmostEqual(window["durationHours"], WINDOW_HOURS, places=4)
        self.assertIn("prior", window["source"])
        self.assertEqual(window["hoursBeforeObservation"], HOURS_BEFORE_OBSERVATION)
        self.assertEqual(self.payload["observedAt"], OBSERVED_AT)


    # --- parameters are reported, not hidden --------------------------------
    def test_every_parameter_is_reported_as_a_prototype_value(self):
        drift = self.payload["drift"]
        self.assertAlmostEqual(drift["windageCoefficient"], FIELD_WINDAGE, places=6)
        self.assertEqual(drift["stepSeconds"], 300.0)
        self.assertEqual(drift["regionBufferKm"], 2.0)
        self.assertIn("backward", drift["integration"])
        self.assertTrue(drift["parametersArePrototypeValues"])
        self.assertEqual(drift["config"]["boundaryStride"], 2)
        self.assertIn("prototype", " ".join(self.payload["notes"]).lower())

    def test_seed_and_sample_counts_are_consistent_with_the_configuration(self):
        ring = self.inputs["slickRing"]
        deduped = ring[:-1] if ring[0] == ring[-1] else ring
        expected_seeds = 1 + len(range(0, len(deduped), 2))
        self.assertEqual(self.origin.seed_count, expected_seeds)
        self.assertGreater(self.origin.sample_count, 0)

    def test_field_summary_records_that_the_field_is_synthetic(self):
        summary = self.payload["drift"]["field"]
        self.assertEqual(summary["provider"], "DemoEnvironmentalProvider")
        self.assertTrue(summary["synthetic"])
        self.assertAlmostEqual(summary["windageCoefficient"], FIELD_WINDAGE, places=6)

    # --- determinism --------------------------------------------------------
    def test_hindcast_is_deterministic(self):
        again = estimate_origin(self.inputs["slickRing"], self.inputs["observedAt"],
                                self.inputs["window"], self.inputs["field"])
        self.assertEqual(json.dumps(again.to_dict(), sort_keys=True),
                         json.dumps(self.payload, sort_keys=True))


class TestOriginFailureModes(unittest.TestCase):
    """A degenerate reconstruction must fail loudly - never collapse to a point."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = load_case_inputs()

    def _estimate(self, ring, observed: str):
        return estimate_origin(ring, observed, self.inputs["window"],
                               self.inputs["field"])

    def test_ring_with_fewer_than_three_vertices_is_rejected(self):
        with self.assertRaises(OriginHindcastError):
            self._estimate([(72.0, 18.0), (72.01, 18.01)], OBSERVED_AT)

    def test_ring_of_identical_positions_cannot_form_a_region(self):
        """A zero-extent slick has no geometry to integrate into a region."""
        with self.assertRaises(OriginHindcastError):
            self._estimate([(72.0, 18.0)] * 3, OBSERVED_AT)

    def test_a_collinear_ring_still_yields_a_2d_region_because_drift_spreads_it(self):
        """Documented behaviour, not an accident: a steady drift fans a line into an area."""
        origin = self._estimate([(72.0, 18.0), (72.05, 18.05), (72.1, 18.1)], OBSERVED_AT)
        self.assertGreater(origin.area_km2, 0.0)
        self.assertGreaterEqual(len(origin.region_ring), 4)

    def test_window_ending_after_the_observation_is_rejected(self):
        """A backward drift needs a window in the past; the future is not a hindcast."""
        future = ReleaseWindow(
            start_epoch=epoch_seconds("2026-03-15T00:00:00Z"),
            end_epoch=epoch_seconds("2026-03-15T06:00:00Z"),
            start_iso="2026-03-15T00:00:00Z", end_iso="2026-03-15T06:00:00Z",
        )
        with self.assertRaises(OriginHindcastError):
            estimate_origin(self.inputs["slickRing"], OBSERVED_AT, future,
                            self.inputs["field"])

    def test_window_shorter_than_one_integration_step_is_rejected(self):
        empty = ReleaseWindow(
            start_epoch=epoch_seconds("2026-03-14T06:00:00Z"),
            end_epoch=epoch_seconds("2026-03-14T06:00:01Z"),
            start_iso="2026-03-14T06:00:00Z", end_iso="2026-03-14T06:00:01Z",
        )
        with self.assertRaises(OriginHindcastError):
            estimate_origin(self.inputs["slickRing"], OBSERVED_AT, empty,
                            self.inputs["field"])

    def test_invalid_configuration_is_rejected(self):
        for kwargs in ({"step_seconds": 0.0}, {"sample_hours": 0.0},
                       {"boundary_stride": 0}, {"region_buffer_km": -1.0},
                       {"windage": 1.5}, {"confidence_spread_reference_km": 0.0}):
            with self.assertRaises(ValueError, msg=f"config {kwargs} must be rejected"):
                OriginConfig(**kwargs)

    def test_config_describes_every_parameter_it_owns(self):
        described = OriginConfig().describe()
        for key in ("stepSeconds", "sampleHours", "windageOverride", "regionBufferKm",
                    "boundaryStride", "confidenceSpreadReferenceKm"):
            self.assertIn(key, described)


class TestEnvironmentalField(unittest.TestCase):
    """The drift field is an interpolator with honest edges, not a magic constant."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = (INTELLIGENCE_DIR / "data" / "demo" / "case_001" / "environmental"
                    / "demo_environmental_field.json")
        cls.field = EnvironmentalField.load(cls.path)

    def test_grid_dimensions_and_labels_are_as_declared(self):
        self.assertGreaterEqual(len(self.field.latitudes), 2)
        self.assertGreaterEqual(len(self.field.longitudes), 2)
        self.assertTrue(self.field.synthetic)
        self.assertEqual(self.field.provider, "DemoEnvironmentalProvider")
        self.assertEqual(self.field.dataset_label, "Synthetic Demonstration Dataset")
        self.assertEqual(self.field.valid_from, "2026-03-11T06:00:00Z")
        self.assertEqual(self.field.valid_to, "2026-03-14T06:00:00Z")

    def test_lookup_at_a_node_reproduces_that_node_exactly(self):
        i, j = 3, 4
        lat, lon = self.field.latitudes[i], self.field.longitudes[j]
        self.assertEqual(self.field.current(lat, lon),
                         (self.field.u_current[i][j], self.field.v_current[i][j]))
        self.assertEqual(self.field.wind(lat, lon),
                         (self.field.u_wind[i][j], self.field.v_wind[i][j]))

    def test_drift_equals_current_plus_windage_times_wind(self):
        lat, lon = self.field.latitudes[3], self.field.longitudes[4]
        u_cur, v_cur = self.field.current(lat, lon)
        u_wind, v_wind = self.field.wind(lat, lon)
        self.assertAlmostEqual(
            u_wind, v_wind, places=9,
            msg="the demo wind is designed to blow from 225 deg (equal components)")
        for windage in (0.0, FIELD_WINDAGE, 0.5, 1.0):
            u, v = self.field.drift(lat, lon, windage)
            self.assertAlmostEqual(u, u_cur + windage * u_wind, places=9)
            self.assertAlmostEqual(v, v_cur + windage * v_wind, places=9)

    def test_drift_step_moves_the_position_downstream(self):
        lat, lon = self.field.latitudes[3], self.field.longitudes[4]
        moved_lat, moved_lon = self.field.drift_step(lat, lon, 3600.0)
        moved_km = haversine_km(lat, lon, moved_lat, moved_lon)
        self.assertGreater(moved_lon, lon, "the eastward current moves longitude forward")
        self.assertGreater(moved_lat, lat, "the northward current moves latitude forward")
        self.assertGreater(moved_km, 0.5)
        self.assertLess(moved_km, 5.0)

    def test_positions_outside_the_grid_are_clamped_not_fatal(self):
        for lat, lon in ((0.0, 0.0), (40.0, 120.0), (-30.0, 10.0)):
            u, v = self.field.drift(lat, lon)
            self.assertIsInstance(u, float)
            self.assertIsInstance(v, float)

    def test_missing_field_file_fails_loudly(self):
        absent = Path(tempfile.gettempdir()) / "abyss-absent-field.json"
        with self.assertRaises(EnvironmentalFieldError):
            EnvironmentalField.load(absent)

    def test_structurally_broken_field_is_rejected(self):
        broken = Path(tempfile.mkdtemp()) / "broken_field.json"
        broken.write_text(json.dumps({"grid": {"latitudes": [17.0, 18.0],
                                               "longitudes": [71.0, 72.0]},
                                      "nodes": []}), encoding="utf-8")
        with self.assertRaises(EnvironmentalFieldError):
            EnvironmentalField.load(broken)

    def test_describe_reports_provenance_without_credentials(self):
        described = self.field.describe()
        self.assertEqual(described["provider"], "DemoEnvironmentalProvider")
        self.assertTrue(described["synthetic"])
        self.assertEqual(described["windageCoefficient"], FIELD_WINDAGE)
        self.assertIn("grid", described)


if __name__ == "__main__":
    unittest.main(verbosity=2)

