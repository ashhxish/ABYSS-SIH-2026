#!/usr/bin/env python3
"""ABYSS Phase 21 - REAL NOAA AIS integration tests.

Runs the REAL NOAA/OAR/PMEL AIS extract through the existing ABYSS AIS engine
and asserts:

  1. real CSV load (raw / accepted / rejected / warning counts)
  2. MMSI set preserved exactly (nothing invented, nothing mutated)
  3. timestamp / lat / lon / SOG / COG / heading preserved per record
  4. spatial selection (real Sentinel-1 scene box, wide box, empty box)
  5. trajectory reconstruction over real MMSIs
  6. transmission-gap detection over those trajectories
  7. POST /ais/real/analyze response schema + envelope
  8. temporalMatchAvailable is always False (no Sentinel-1 timestamp)
  9. no synthetic CASE-001 leakage into real-AIS output
 10. bounding-box / missing-file error handling
 11. determinism
 12. CASE-001 regression (baseline ranking unchanged)
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd

INTELLIGENCE_DIR = Path(__file__).resolve().parent.parent
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from app.ais.real_ais import (  # noqa: E402
    REAL_AIS_CSV_ENV,
    REAL_AIS_LABEL,
    REAL_AIS_SOURCE,
    SENTINEL1_SCENE_BBOX,
    TEMPORAL_MATCH_REASON,
    RealAisError,
    analyse_real_ais,
    normalise_bbox,
    point_in_bbox,
    scene_bbox,
    to_canonical_frame,
)
from app.ingestion import SYNTHETIC_LABEL, ingest_ais_csv  # noqa: E402

#: Verified baseline of the real extract shipped at ~/SIH/real_ais/ais_sample.csv
REAL_AIS_CSV = Path(
    os.environ.get(REAL_AIS_CSV_ENV, str(Path.home() / "SIH" / "real_ais" / "ais_sample.csv"))
).expanduser()
REAL_AVAILABLE = REAL_AIS_CSV.is_file()
requires_real = unittest.skipUnless(REAL_AVAILABLE, f"real AIS extract not found at {REAL_AIS_CSV}")

EXPECTED_RAW_RECORDS = 3039
EXPECTED_ACCEPTED_RECORDS = 3034
EXPECTED_REJECTED_RECORDS = 5
EXPECTED_WARNING_COUNT = 656
EXPECTED_UNIQUE_MMSI = 815

#: Spatial test regions
WIDE_BBOX: Tuple[float, float, float, float] = (-96.0, 21.5, -93.0, 24.5)
EMPTY_BBOX: Tuple[float, float, float, float] = (0.0, 0.0, 0.1, 0.1)

_CACHE: Dict[str, Any] = {}


def real_analysis() -> Dict[str, Any]:
    """Run the full real-AIS analysis once and reuse it across tests."""
    if "default" not in _CACHE:
        _CACHE["default"] = analyse_real_ais()
    return _CACHE["default"]


def raw_rows_by_key() -> Dict[Tuple[str, pd.Timestamp], Any]:
    """Index the raw extract rows by (MMSI, UTC instant) for verbatim comparison."""
    frame = pd.read_csv(REAL_AIS_CSV, dtype=str, keep_default_na=False, na_filter=False)
    rows: Dict[Tuple[str, pd.Timestamp], Any] = {}
    for _, row in frame.iterrows():
        stamp = pd.to_datetime(row["time"], utc=True, errors="coerce")
        if pd.isna(stamp):
            continue
        rows[(str(row["MMSI"]).strip(), pd.Timestamp(stamp))] = row
    return rows


@requires_real
class TestRealAisLoad(unittest.TestCase):
    """Targets 1-2: the real extract loads through the existing engine."""

    def test_01_extract_exists(self) -> None:
        self.assertTrue(REAL_AIS_CSV.is_file(), REAL_AIS_CSV)
        self.assertGreater(REAL_AIS_CSV.stat().st_size, 0)

    def test_02_load_and_validation_counts(self) -> None:
        result = real_analysis()
        self.assertEqual(result["rawRecordCount"], EXPECTED_RAW_RECORDS)
        self.assertEqual(result["acceptedRecordCount"], EXPECTED_ACCEPTED_RECORDS)
        self.assertEqual(result["rejectedRecordCount"], EXPECTED_REJECTED_RECORDS)
        self.assertEqual(result["warningCount"], EXPECTED_WARNING_COUNT)
        self.assertEqual(result["uniqueMmsiCount"], EXPECTED_UNIQUE_MMSI)
        # raw = accepted + rejected, i.e. no row vanished or was duplicated
        self.assertEqual(
            result["rawRecordCount"],
            result["acceptedRecordCount"] + result["rejectedRecordCount"],
        )

    def test_03_row_count_matches_file(self) -> None:
        with REAL_AIS_CSV.open(encoding="utf-8") as handle:
            data_rows = sum(1 for _ in handle) - 1  # minus header
        self.assertEqual(data_rows, EXPECTED_RAW_RECORDS)
        self.assertEqual(real_analysis()["rawRecordCount"], data_rows)

    def test_04_mmsi_set_preserved_exactly(self) -> None:
        raw = pd.read_csv(REAL_AIS_CSV, dtype=str, keep_default_na=False, na_filter=False)
        result = real_analysis()
        analysed = set(result["uniqueMmsi"])
        self.assertEqual(len(analysed), EXPECTED_UNIQUE_MMSI)
        # every analysed MMSI really exists in the raw extract (nothing invented)
        self.assertTrue(analysed.issubset(set(raw["MMSI"].str.strip())))
        # every accepted MMSI is a 9-digit Maritime Identification Digit
        for mmsi in analysed:
            self.assertRegex(mmsi, r"^\d{9}$")

    def test_05_provenance_is_real_not_synthetic(self) -> None:
        result = real_analysis()
        self.assertTrue(result["realAis"])
        self.assertFalse(result["source"]["synthetic"])
        self.assertEqual(result["source"]["provider"], REAL_AIS_SOURCE)
        self.assertEqual(Path(result["source"]["uri"]).name, REAL_AIS_CSV.name)
        self.assertNotIn(SYNTHETIC_LABEL, result["source"]["datasetLabels"])

    def test_06_records_preserve_raw_values(self) -> None:
        """Timestamp / lat / lon / SOG / COG / heading survive the hand-off verbatim."""
        batch = ingest_ais_csv(REAL_AIS_CSV)
        raw_rows = raw_rows_by_key()
        compared = 0
        for record in batch.records[:400]:
            row = raw_rows.get((record.mmsi, pd.Timestamp(record.timestamp)))
            if row is None:
                continue
            compared += 1
            self.assertAlmostEqual(record.latitude, float(row["Lat"]), places=5)
            self.assertAlmostEqual(record.longitude, float(row["Lon"]), places=5)
            sog = float(row["SOG"])
            if sog == 102.3:  # AIS "not available" sentinel -> None, never a number
                self.assertIsNone(record.sogKn)
            else:
                self.assertAlmostEqual(record.sogKn, sog, places=3)
            cog = float(row["COG"])
            self.assertIsNone(record.cogDeg) if cog == 360.0 else self.assertAlmostEqual(
                record.cogDeg, cog, places=3
            )
            heading = float(row["Heading"])
            self.assertIsNone(record.headingDeg) if heading == 511 else self.assertAlmostEqual(
                record.headingDeg, heading, places=3
            )
        self.assertGreater(compared, 200)

    def test_07_canonical_frame_has_audit_line_numbers(self) -> None:
        batch = ingest_ais_csv(REAL_AIS_CSV)
        frame, notes = to_canonical_frame(batch, EXPECTED_RAW_RECORDS)
        self.assertEqual(len(frame), EXPECTED_ACCEPTED_RECORDS)
        self.assertEqual(notes, [])  # raw source lines reconstructed for every row
        lines = frame["_line"].tolist()
        self.assertEqual(len(set(lines)), len(lines))  # unique
        self.assertGreater(min(lines), 1)
        self.assertLessEqual(max(lines), EXPECTED_RAW_RECORDS + 1)
        self.assertNotIn(0, frame["_order"].tolist()[1:] if len(frame) > 1 else [])


@requires_real
class TestRealAisSpatial(unittest.TestCase):
    """Targets 4 and 10: bounding-box selection behaves honestly."""

    def test_08_scene_bbox_selects_a_real_position(self) -> None:
        result = real_analysis()
        self.assertTrue(result["spatialFilterApplied"])
        self.assertEqual(tuple(result["spatialBBox"]), SENTINEL1_SCENE_BBOX)
        # ONE real position of the whole extract falls inside the Sentinel-1 scene
        self.assertEqual(result["spatialMatchCount"], 1)
        self.assertEqual(result["filteredRecordCount"], result["spatialMatchCount"])
        self.assertEqual(result["vesselCount"], 1)
        vessel = result["vessels"][0]
        self.assertEqual(vessel["mmsi"], "309987000")
        self.assertEqual(vessel["vesselName"], "LILLESAND")
        self.assertEqual(vessel["matchedPointCount"], 1)
        self.assertFalse(vessel["synthetic"])
        self.assertEqual(vessel["datasetLabel"], REAL_AIS_SOURCE)
        self.assertEqual(vessel["matchedStartTimestamp"], "2024-05-29T01:15:52Z")
        # the matched position itself lies inside the Sentinel-1 scene bounds
        self.assertTrue(
            point_in_bbox(
                vessel["matchedLastPosition"]["latitude"],
                vessel["matchedLastPosition"]["longitude"],
                SENTINEL1_SCENE_BBOX,
            )
        )
        self.assertFalse(
            point_in_bbox(
                vessel["firstPosition"]["latitude"],
                vessel["firstPosition"]["longitude"],
                SENTINEL1_SCENE_BBOX,
            )
        )

    def test_09_wide_bbox_selects_more_traffic(self) -> None:
        result = analyse_real_ais(bbox=list(WIDE_BBOX))
        self.assertEqual(result["spatialMatchCount"], result["filteredRecordCount"])
        self.assertGreater(result["spatialMatchCount"], 1)
        self.assertGreater(result["vesselCount"], 1)
        self.assertEqual(result["vesselCount"], len(result["vessels"]))
        for vessel in result["vessels"][:20]:
            self.assertGreaterEqual(vessel["matchedPointCount"], 1)
            self.assertLessEqual(vessel["matchedPointCount"], vessel["pointCount"])

    def test_10_empty_bbox_returns_zero_without_fabrication(self) -> None:
        result = analyse_real_ais(bbox=list(EMPTY_BBOX))
        self.assertEqual(result["spatialMatchCount"], 0)
        self.assertEqual(result["filteredRecordCount"], 0)
        self.assertEqual(result["vesselCount"], 0)
        self.assertEqual(result["vessels"], [])
        self.assertTrue(any("No real AIS position" in warning for warning in result["warnings"]))
        # the extract-wide engine results are untouched by an empty region
        self.assertEqual(result["trajectoryCount"], EXPECTED_UNIQUE_MMSI)
        self.assertGreater(result["gapCount"], 0)

    def test_11_no_spatial_filter_keeps_whole_extract(self) -> None:
        result = analyse_real_ais(spatial_filter=False)
        self.assertFalse(result["spatialFilterApplied"])
        self.assertIsNone(result["spatialBBox"])
        self.assertEqual(result["spatialMatchCount"], EXPECTED_ACCEPTED_RECORDS)
        self.assertEqual(result["vesselCount"], EXPECTED_UNIQUE_MMSI)
        self.assertEqual(
            result["analysis"]["spatial"]["matchedTrajectoryCount"], EXPECTED_UNIQUE_MMSI
        )

    def test_12_bbox_validation_and_point_test(self) -> None:
        self.assertTrue(point_in_bbox(22.4, -93.4, SENTINEL1_SCENE_BBOX))
        self.assertFalse(point_in_bbox(22.4, -93.6, SENTINEL1_SCENE_BBOX))
        self.assertFalse(point_in_bbox(30.0, -93.4, SENTINEL1_SCENE_BBOX))
        self.assertEqual(normalise_bbox(None), SENTINEL1_SCENE_BBOX)
        self.assertEqual(scene_bbox(), SENTINEL1_SCENE_BBOX)
        with self.assertRaises(RealAisError):
            normalise_bbox([1.0, 2.0, 3.0])  # wrong length
        with self.assertRaises(RealAisError):
            normalise_bbox([10.0, 2.0, 3.0, 4.0])  # west > east
        with self.assertRaises(RealAisError):
            normalise_bbox([1.0, 40.0, 3.0, 20.0])  # south > north
        with self.assertRaises(RealAisError):
            normalise_bbox([200.0, 0.0, 3.0, 4.0])  # longitude out of range


@requires_real
class TestRealAisTrajectoriesAndGaps(unittest.TestCase):
    """Targets 5-6: real MMSI tracks and transmission gaps."""

    def test_13_one_trajectory_per_real_mmsi(self) -> None:
        result = real_analysis()
        self.assertEqual(result["trajectoryCount"], EXPECTED_UNIQUE_MMSI)
        trajectories = result["analysis"]["trajectories"]
        self.assertEqual(trajectories["skippedRecordCount"], 0)
        self.assertEqual(trajectories["statistics"]["counts"]["records"], EXPECTED_ACCEPTED_RECORDS)
        self.assertEqual(trajectories["statistics"]["counts"]["vessels"], EXPECTED_UNIQUE_MMSI)
        self.assertEqual(trajectories["statistics"]["counts"]["syntheticRecords"], 0)

    def test_14_vessel_features_come_from_the_engine(self) -> None:
        result = analyse_real_ais(bbox=list(WIDE_BBOX))
        self.assertTrue(result["vessels"])
        for vessel in result["vessels"][:30]:
            self.assertGreater(vessel["pointCount"], 0)
            self.assertLessEqual(vessel["startTimestamp"], vessel["endTimestamp"])
            self.assertRegex(vessel["mmsi"], r"^\d{9}$")
            if vessel["meanSogKn"] is not None and vessel["maxSogKn"] is not None:
                self.assertLessEqual(vessel["meanSogKn"], vessel["maxSogKn"])
                self.assertGreaterEqual(vessel["meanSogKn"], 0.0)
            self.assertGreaterEqual(vessel["gapCount"], 0)

    def test_15_transmission_gaps_detected(self) -> None:
        result = real_analysis()
        self.assertGreater(result["gapCount"], 0)
        self.assertEqual(
            result["gapCount"],
            result["analysis"]["trajectories"]["statistics"]["counts"]["gaps"],
        )
        wide = analyse_real_ais(bbox=list(WIDE_BBOX))
        # gap detection is extract-wide, so spatial selection must not change it
        self.assertEqual(wide["gapCount"], result["gapCount"])
        self.assertGreater(wide["analysis"]["spatial"]["matchedGapCount"], 0)
        self.assertLessEqual(wide["analysis"]["spatial"]["matchedGapCount"], result["gapCount"])

    def test_16_temporal_selection_is_not_a_sentinel1_match(self) -> None:
        result = analyse_real_ais(
            bbox=list(WIDE_BBOX),
            start_time="2024-05-06T00:00:00Z",
            end_time="2024-05-07T00:00:00Z",
        )
        self.assertLess(result["analysis"]["cleaning"]["recordCount"], EXPECTED_ACCEPTED_RECORDS)
        self.assertFalse(result["temporalMatchAvailable"])
        self.assertEqual(result["temporalMatchReason"], TEMPORAL_MATCH_REASON)
        self.assertTrue(any("extract-internal selection" in note for note in result["notes"]))

    def test_17_bad_time_and_missing_file_raise(self) -> None:
        with self.assertRaises(RealAisError):
            analyse_real_ais(start_time="not-an-instant")
        with self.assertRaises(RealAisError):
            analyse_real_ais(source_path=str(REAL_AIS_CSV.parent / "does_not_exist.csv"))

    def test_18_analysis_is_deterministic(self) -> None:
        first = analyse_real_ais(bbox=list(WIDE_BBOX))
        second = analyse_real_ais(bbox=list(WIDE_BBOX))
        for key in (
            "rawRecordCount",
            "acceptedRecordCount",
            "rejectedRecordCount",
            "warningCount",
            "uniqueMmsiCount",
            "spatialMatchCount",
            "vesselCount",
            "trajectoryCount",
            "gapCount",
        ):
            self.assertEqual(first[key], second[key], key)
        self.assertEqual(
            [vessel["mmsi"] for vessel in first["vessels"]],
            [vessel["mmsi"] for vessel in second["vessels"]],
        )


@requires_real
class TestRealAisNoSyntheticLeakage(unittest.TestCase):
    """Target 9: synthetic CASE-001 data can never appear in real-AIS output."""

    def test_19_no_case001_records_or_labels(self) -> None:
        result = real_analysis()
        for mmsi in result["uniqueMmsi"]:
            self.assertFalse(mmsi.startswith("90000000"), f"demo MMSI leaked: {mmsi}")
        for vessel in result["vessels"]:
            self.assertFalse(vessel["mmsi"].startswith("90000000"))
        self.assertEqual(result["analysis"]["dataQuality"]["syntheticRecordCount"], 0)
        self.assertNotIn(SYNTHETIC_LABEL, result["source"]["datasetLabels"])
        for vessel in result["vessels"]:
            self.assertFalse(vessel["synthetic"])
            self.assertEqual(vessel["datasetLabel"], REAL_AIS_SOURCE)
        # the only mention of CASE-001 is the guard note, never a record or a label
        payload = json.dumps(result, default=str)
        self.assertNotIn(SYNTHETIC_LABEL, payload)
        self.assertTrue(
            any("no synthetic CASE-001 record" in note for note in result["notes"])
        )
        self.assertEqual(payload.count("CASE-001"), 1)

    def test_20_no_responsibility_or_ranking_output(self) -> None:
        result = real_analysis()
        payload = json.dumps(result, default=str)
        for banned in ("totalScore", "\"ranking\"", "\"candidates\"", "culprit"):
            self.assertNotIn(banned, payload)
        self.assertFalse(result["temporalMatchAvailable"])
        self.assertEqual(result["label"], REAL_AIS_LABEL)

    def test_21_payload_is_json_serialisable(self) -> None:
        # the API returns this dict verbatim, so it must not need a fallback encoder
        result = analyse_real_ais(bbox=list(WIDE_BBOX))
        payload = json.dumps(result)
        self.assertIn("temporalMatchAvailable", payload)


@requires_real
class TestRealAisEndpoint(unittest.TestCase):
    """Targets 7-8: POST /ais/real/analyze schema and the temporal limitation."""

    @classmethod
    def setUpClass(cls) -> None:
        from fastapi.testclient import TestClient

        from app.main import app

        cls.client = TestClient(app)

    def _assert_envelope(self, data: Dict[str, Any]) -> None:
        self.assertIn("dataSource", data)
        self.assertIsInstance(data["dataSource"], str)
        self.assertIn("warnings", data)
        self.assertIsInstance(data["warnings"], list)

    def test_22_endpoint_default_is_the_scene_bbox(self) -> None:
        response = self.client.post("/ais/real/analyze", json={})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self._assert_envelope(data)
        for key in (
            "label",
            "realAis",
            "source",
            "temporalMatchAvailable",
            "temporalMatchReason",
            "rawRecordCount",
            "acceptedRecordCount",
            "rejectedRecordCount",
            "warningCount",
            "uniqueMmsiCount",
            "filteredRecordCount",
            "vesselCount",
            "trajectoryCount",
            "gapCount",
            "spatialFilterApplied",
            "spatialBBox",
            "spatialMatchCount",
            "vessels",
            "analysis",
        ):
            self.assertIn(key, data, key)
        self.assertEqual(data["dataSource"], REAL_AIS_SOURCE)
        self.assertEqual(data["label"], REAL_AIS_LABEL)
        self.assertTrue(data["realAis"])
        self.assertEqual(data["rawRecordCount"], EXPECTED_RAW_RECORDS)
        self.assertEqual(data["acceptedRecordCount"], EXPECTED_ACCEPTED_RECORDS)
        self.assertEqual(data["rejectedRecordCount"], EXPECTED_REJECTED_RECORDS)
        self.assertTrue(data["spatialFilterApplied"])
        self.assertEqual(tuple(data["spatialBBox"]), SENTINEL1_SCENE_BBOX)

    def test_23_endpoint_never_claims_a_temporal_match(self) -> None:
        for body in ({}, {"bbox": list(WIDE_BBOX)}, {"bbox": list(EMPTY_BBOX)}):
            data = self.client.post("/ais/real/analyze", json=body).json()
            self.assertIs(data["temporalMatchAvailable"], False)
            self.assertEqual(data["temporalMatchReason"], TEMPORAL_MATCH_REASON)

    def test_24_endpoint_wide_bbox_and_vessel_flag(self) -> None:
        data = self.client.post(
            "/ais/real/analyze",
            json={"bbox": list(WIDE_BBOX), "includeVessels": False},
        ).json()
        self.assertGreater(data["spatialMatchCount"], 1)
        self.assertGreater(data["vesselCount"], 1)
        self.assertEqual(data["vessels"], [])  # includeVessels=False
        self.assertEqual(data["spatialBBox"], list(WIDE_BBOX))

    def test_25_endpoint_exposes_sanitised_issue_sample(self) -> None:
        data = self.client.post("/ais/real/analyze", json={}).json()
        ingestion = data["analysis"]["ingestion"]
        self.assertEqual(ingestion["contract"], "ais")
        self.assertEqual(ingestion["rejectedRecordCount"], EXPECTED_REJECTED_RECORDS)
        self.assertEqual(ingestion["warningCount"], EXPECTED_WARNING_COUNT)
        self.assertEqual(len(ingestion["warningsSample"]), 50)
        self.assertLessEqual(len(ingestion["issues"]), 20)

    def test_26_endpoint_bad_request_is_rejected(self) -> None:
        response = self.client.post("/ais/real/analyze", json={"bbox": [1.0, 2.0, 3.0]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("bbox", response.json()["detail"])

    def test_27_endpoint_is_in_the_openapi_schema(self) -> None:
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/ais/real/analyze", schema["paths"])
        operation = schema["paths"]["/ais/real/analyze"]["post"]
        self.assertIn("post", schema["paths"]["/ais/real/analyze"])
        ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        self.assertEqual(ref, "#/components/schemas/RealAisAnalyzeResponse")


class TestCase001Regression(unittest.TestCase):
    """Target 12: the synthetic CASE-001 baseline is untouched by this phase."""

    def test_28_case001_ranking_baseline(self) -> None:
        from app.investigation import run_investigation

        payload = run_investigation().to_dict()
        entries = payload["ranking"]["entries"]
        self.assertEqual(len(entries), 12)
        self.assertEqual(
            [entry["mmsi"] for entry in entries[:4]],
            ["900000001", "900000002", "900000003", "900000004"],
        )
        self.assertAlmostEqual(entries[0]["totalScore"], 83.564, places=2)
        self.assertAlmostEqual(entries[1]["totalScore"], 83.200, places=2)
        self.assertAlmostEqual(entries[2]["totalScore"], 80.125, places=2)
        self.assertAlmostEqual(entries[3]["totalScore"], 0.000, places=2)

    def test_29_demo_ais_cleaning_unchanged(self) -> None:
        from app.ais.cleaning import clean_demo_case

        cleaning = clean_demo_case()
        self.assertTrue(cleaning.source["synthetic"])
        self.assertGreater(len(cleaning.records), 0)
        self.assertTrue(
            all(
                record.get("datasetLabel") == SYNTHETIC_LABEL
                for record in cleaning.records[:50]
            )
        )


if __name__ == "__main__":
    unittest.main()






