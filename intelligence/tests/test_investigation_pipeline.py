#!/usr/bin/env python3
"""ABYSS - end-to-end tests for the investigation orchestrator (Phases 5-11 assembled).

WHAT THESE TESTS PROVE
    1. one call runs the whole chain - cleaning, trajectories, origin hindcast,
       compatibility, behaviour, gaps, scoring, ranking - and returns twelve explained
       candidates whose statistics reconcile with the upstream phases (3,666 cleaned
       records, 2 gaps judged, 3 vessels inside the region during the window, 12 scored)
    2. the answer keys are not inputs. demo_origin_expected.json and
       expected_ranking.json are temporarily renamed away and the pipeline is re-run: the
       output is byte-identical without them. The reconstruction is therefore a genuine
       function of the slick, the environmental field and the AIS data, and the fixtures
       are read by the test suite only
    3. the result is labelled and bounded in the way the specification demands: the
       dataset label and the verbatim synthetic disclaimer travel with it, the synthetic
       notice and cleaning warnings are present, the eight methodology limitations are
       attached, and nothing in the payload asserts guilt or publishes a release POINT
    4. specification cases A-G are satisfied end to end, each mapped to the vessel the
       scenario designed for it
    5. the run is deterministic: repeated executions produce identical JSON, and the
       command line interface produces the same ranking as the library call - including
       under re-weighted evidence, where the gap-compatible candidate takes the lead

WHAT THESE TESTS DO NOT DO
    They do not re-test the individual phases; each has its own module. They check that
    the assembled product behaves as the specification describes.

RUN (needs the project virtual environment)
    .venv/bin/python -m unittest discover -s intelligence/tests -v
    .venv/bin/python intelligence/tests/test_investigation_pipeline.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

INTELLIGENCE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = INTELLIGENCE_DIR.parent
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from app.investigation import InvestigationError, load_case_inputs, run_investigation

CASE_DIR = INTELLIGENCE_DIR / "data" / "demo" / "case_001"
VESSEL_IDS = [f"V{index:03d}" for index in range(1, 13)]
EXPECTED_STATISTICS = {
    "vesselsScored": 12,
    "recordsCleaned": 3666,
    "insideRegionDuringWindow": 3,
    "gapsJudged": 2,
    "behaviourAnomaliesReported": 4,
    "weightsTotal": 100.0,
    "tieGroupCount": 1,
    "topCandidateMmsi": "900000001",
}
FORBIDDEN_KEYS = ("truereleasepoint", "expectedoriginregion", "nominalreleasetime")


def run_payload(**kwargs) -> dict:
    return run_investigation(**kwargs).to_dict()


def all_keys(payload) -> list:
    """Every dict key in a nested payload, lower-cased."""
    names = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            names.append(str(key).lower())
            names.extend(all_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            names.extend(all_keys(item))
    return names


class TestAssembledResult(unittest.TestCase):
    """What one pipeline call returns, and that its numbers reconcile."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = run_payload()
        cls.entries = cls.payload["ranking"]["entries"]
        cls.by_vessel = {entry["vesselId"]: entry for entry in cls.entries}

    def test_twelve_candidates_are_returned_and_ranked(self):
        self.assertEqual(len(self.entries), 12)
        self.assertEqual({entry["vesselId"] for entry in self.entries}, set(VESSEL_IDS))
        self.assertEqual(sorted(entry["rank"] for entry in self.entries),
                         list(range(1, 13)))
        self.assertEqual(self.entries[0]["vesselId"], "V001")

    def test_statistics_reconcile_with_the_upstream_phases(self):
        statistics = self.payload["statistics"]
        for key, value in EXPECTED_STATISTICS.items():
            self.assertEqual(statistics[key], value, key)

    def test_the_origin_is_reported_as_a_region_with_a_window(self):
        origin = self.payload["origin"]
        self.assertEqual(origin["region"]["geometry"]["type"], "Polygon")
        self.assertGreater(origin["region"]["areaKm2"], 0.0)
        self.assertGreater(origin["region"]["spreadKm"], 0.0)
        self.assertEqual(origin["releaseWindow"]["start"], "2026-03-13T10:00:00Z")
        self.assertEqual(origin["releaseWindow"]["end"], "2026-03-13T18:00:00Z")
        self.assertEqual(origin["observedAt"], "2026-03-14T06:00:00Z")

    def test_every_candidate_carries_the_assessments_behind_its_score(self):
        for entry in self.entries:
            for key in ("compatibility", "behaviour", "gapAnalysis", "counterfactual",
                        "factors", "reasons"):
                self.assertIn(key, entry, f"{entry['vesselId']} missing {key}")
            self.assertIn("filters", entry["compatibility"])
            self.assertIn("gaps", entry["gapAnalysis"])

    def test_no_candidate_publishes_a_release_point_or_asserts_guilt(self):
        names = all_keys(self.payload)
        for forbidden in FORBIDDEN_KEYS:
            self.assertNotIn(forbidden, names, f"answer-key field {forbidden} leaked")
        text = json.dumps(self.payload).lower()
        for forbidden in ("guilty", "caused the spill", "responsible for the spill",
                          "illegal discharge confirmed"):
            self.assertNotIn(forbidden, text)

    def test_the_configuration_actually_used_is_reported_back(self):
        config = self.payload["config"]
        self.assertEqual(set(config), {"scoring", "compatibility", "behaviour",
                                      "gapAnalysis"})
        self.assertEqual(self.payload["weights"], {"spatial": 35.0, "gap": 10.0,
                                                   "trajectory": 20.0, "behaviour": 10.0,
                                                   "temporal": 25.0})
        self.assertEqual(config["scoring"]["spatialFalloffKm"],
                         config["compatibility"]["spatialFalloffKm"])

    def test_the_result_is_json_serialisable(self):
        json.dumps(self.payload)

    def test_the_payload_is_labelled_as_demo_data(self):
        self.assertTrue(self.payload["synthetic"])
        self.assertEqual(self.payload["datasetLabel"], "Synthetic Demonstration Dataset")
        self.assertEqual(self.payload["caseId"], "CASE-001")
        self.assertEqual(self.payload["module"], "investigation")
        self.assertTrue(any("synthetic demonstration data (DEMO DATA)" in warning
                            for warning in self.payload["warnings"]))
        self.assertEqual(self.payload["source"]["provider"], "DemoAISProvider")



class TestAnswerKeysAreNotInputs(unittest.TestCase):
    """The strongest available proof that reconstruction is not answer-reading."""

    def test_output_is_identical_when_the_answer_keys_are_absent(self):
        baseline = run_payload()
        fixtures = [CASE_DIR / "demo_origin_expected.json",
                    CASE_DIR / "expected_ranking.json"]
        renamed = []
        try:
            for fixture in fixtures:
                hidden = fixture.with_suffix(fixture.suffix + ".hidden")
                fixture.rename(hidden)
                renamed.append((fixture, hidden))
            without_keys = run_payload()
        finally:
            for fixture, hidden in renamed:
                hidden.rename(fixture)
        for fixture, _ in renamed:
            self.assertTrue(fixture.exists(), f"{fixture.name} must be restored")
        self.assertEqual(json.dumps(without_keys, sort_keys=True),
                         json.dumps(baseline, sort_keys=True))

    def test_the_pipeline_states_that_answer_keys_are_never_read(self):
        notes = " ".join(run_payload()["notes"])
        self.assertIn("scenario answer keys are never read by this pipeline", notes)

    def test_the_reconstructed_region_is_not_the_answer_key_ellipse(self):
        """Same neighbourhood, different geometry: a hull of drifted particles, not a copy."""
        key = json.loads((CASE_DIR / "demo_origin_expected.json").read_text("utf-8"))
        expected_ring = key["expectedOriginRegion"]["coordinates"][0]
        measured_ring = run_payload()["origin"]["region"]["geometry"]["coordinates"][0]
        self.assertNotEqual(len(expected_ring), len(measured_ring))
        self.assertNotEqual(expected_ring[0], measured_ring[0])

    def test_the_case_bundle_reserves_the_fixture_for_tests_only(self):
        """The bundle itself declares that the answer key is never a pipeline input."""
        case = json.loads((CASE_DIR / "case_001.json").read_text(encoding="utf-8"))
        self.assertEqual(case["reservedOriginFixtureFile"], "demo_origin_expected.json")
        note = case["reservedOriginFixtureNote"].lower()
        self.assertIn("not an input to the analysis pipeline", note)
        self.assertIn("never be surfaced", note)


class TestScenarioCasesEndToEnd(unittest.TestCase):
    """Specification cases A-G, measured on the assembled result."""

    @classmethod
    def setUpClass(cls) -> None:
        payload = run_payload()
        cls.entries = payload["ranking"]["entries"]
        cls.by_vessel = {entry["vesselId"]: entry for entry in cls.entries}
        cls.rank = {vessel: entry["rank"] for vessel, entry in cls.by_vessel.items()}

    def points(self, vessel: str, factor: str) -> float:
        return self.by_vessel[vessel]["factors"][factor]["points"]

    def test_case_a_v001_is_compatible_in_location_time_and_movement(self):
        entry = self.by_vessel["V001"]
        self.assertEqual(self.points("V001", "spatial"), 35.0)
        self.assertEqual(self.points("V001", "temporal"), 25.0)
        self.assertEqual(self.points("V001", "trajectory"), 20.0)
        self.assertGreater(self.points("V001", "behaviour"), 0.0)
        self.assertEqual(entry["gapAnalysis"]["hasGap"], False)
        self.assertLessEqual(self.rank["V001"], 2)

    def test_case_b_v005_has_the_right_place_but_the_wrong_time(self):
        entry = self.by_vessel["V005"]
        self.assertTrue(entry["compatibility"]["insideRegionAnytime"])
        self.assertFalse(entry["compatibility"]["insideRegionDuringWindow"])
        self.assertEqual(entry["compatibility"]["insideRegionRelation"], "after_window")
        self.assertEqual(self.points("V005", "temporal"), 0.0)
        self.assertEqual(entry["totalScore"], 0.0)
        self.assertGreater(self.rank["V005"], self.rank["V001"])

    def test_case_c_wrong_location_with_the_right_time_scores_no_spatial_evidence(self):
        entry = self.by_vessel["V006"]
        self.assertGreater(entry["compatibility"]["recordsInWindow"], 0)
        self.assertEqual(self.points("V006", "spatial"), 0.0)
        self.assertEqual(self.points("V006", "temporal"), 0.0)
        self.assertEqual(entry["totalScore"], 0.0)

    def test_case_d_v003s_impossible_gap_contributes_nothing(self):
        self.assertEqual(self.by_vessel["V003"]["gapAnalysis"]["gapCount"], 1)
        self.assertEqual(self.by_vessel["V003"]["gapAnalysis"]["anyFeasible"], False)
        self.assertEqual(self.points("V003", "gap"), 0.0)
        self.assertGreater(self.rank["V003"], self.rank["V002"])

    def test_case_e_v002s_compatible_gap_contributes_but_stays_capped(self):
        self.assertEqual(self.by_vessel["V002"]["gapAnalysis"]["anyFeasible"], True)
        self.assertEqual(self.points("V002", "gap"), 3.0)
        self.assertLess(self.points("V002", "gap"),
                        self.by_vessel["V002"]["factors"]["gap"]["maxPoints"])
        self.assertLessEqual(self.rank["V002"], 2)   # top-2 with the gap contributing
        self.assertLess(self.rank["V002"], self.rank["V003"])

    def test_case_f_a_strong_anomaly_alone_cannot_rank_a_vessel_highly(self):
        entry = self.by_vessel["V006"]
        self.assertTrue(entry["behaviour"]["isAnomaly"])
        self.assertGreater(entry["behaviour"]["rawAnomaly"], 0.30)
        self.assertEqual(self.points("V006", "behaviour"), 0.0)
        self.assertGreater(self.rank["V006"], 5)

    def test_case_g_the_nearest_vessel_to_the_slick_is_not_the_top_candidate(self):
        nearest = min(self.entries, key=lambda item: item["distanceToSlickKm"])
        self.assertEqual(nearest["vesselId"], "V004")
        self.assertNotEqual(nearest["rank"], 1)
        self.assertLess(nearest["totalScore"], self.entries[0]["totalScore"])



class TestDeterminismAndLimitations(unittest.TestCase):
    """Reproducibility and the honesty appendix the specification requires."""

    def test_repeated_runs_produce_identical_results(self):
        first = run_payload()
        second = run_payload()
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    def test_the_verbatim_case_disclaimer_travels_with_the_result(self):
        payload = run_payload()
        case = json.loads((CASE_DIR / "case_001.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["disclaimer"], case["disclaimer"])
        self.assertIn("does not establish legal responsibility", payload["disclaimer"])
        self.assertIn("synthetic", payload["disclaimer"])

    def test_the_methodology_limitations_are_attached_to_every_result(self):
        limitations = " ".join(run_payload()["limitations"]).lower()
        for required in ("prototype drift model", "windage", "candidate-window prior",
                         "ais coverage is uneven", "gap", "prototype"):
            self.assertIn(required, limitations, f"limitation about {required} missing")

    def test_cleaning_warnings_are_carried_into_the_investigation_report(self):
        warnings = " ".join(run_payload()["warnings"])
        self.assertIn("rejected during cleaning", warnings)
        self.assertIn("nothing was dropped silently", warnings)

    def test_a_missing_case_directory_fails_loudly(self):
        empty = Path(tempfile.mkdtemp())
        with self.assertRaises(InvestigationError):
            load_case_inputs(case_dir=empty)


class TestCommandLineInterface(unittest.TestCase):
    """The documented CLI must reproduce the library result and honour weight flags."""

    def _run_cli(self, *args, env=None):
        return subprocess.run(
            [sys.executable, "-m", "app.investigation", "--quiet", *args],
            cwd=str(INTELLIGENCE_DIR), capture_output=True, text=True,
            env={**os.environ, **(env or {})},
        )

    def test_cli_writes_the_same_ranking_as_the_library_call(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "investigation.json"
            completed = self._run_cli("--json", str(out))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            cli_payload = json.loads(out.read_text(encoding="utf-8"))
        library = run_payload()
        self.assertEqual([entry["vesselId"] for entry in cli_payload["ranking"]["entries"]],
                         [entry["vesselId"] for entry in library["ranking"]["entries"]])
        self.assertEqual([entry["totalScore"] for entry in cli_payload["ranking"]["entries"]],
                         [entry["totalScore"] for entry in library["ranking"]["entries"]])
        self.assertEqual(cli_payload["statistics"], library["statistics"])

    def test_cli_weight_overrides_change_which_evidence_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "gap_only.json"
            completed = self._run_cli("--json", str(out), "--weight-spatial", "0",
                                      "--weight-gap", "100", "--weight-trajectory", "0",
                                      "--weight-behaviour", "0", "--weight-temporal", "0")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["weights"]["gap"], 100.0)
        self.assertEqual(payload["ranking"]["entries"][0]["vesselId"], "V002")
        self.assertEqual(payload["ranking"]["entries"][0]["totalScore"], 30.0)

    def test_cli_reports_a_missing_case_bundle_with_exit_code_two(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = self._run_cli("--json", str(Path(directory) / "none.json"),
                                      env={"ABYSS_DATA_DIR": directory})
            self.assertEqual(completed.returncode, 2)
            self.assertIn("error:", completed.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)

