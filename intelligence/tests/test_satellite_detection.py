#!/usr/bin/env python3
"""ABYSS - unit tests for satellite observation & slick detection (Phase 12).

PROVES:
    1. Demo scenario loads and validates without network or imagery processing.
    2. Characterisation metrics (area, centroid, bounding box, perimeter) are computed
       and closely match expected synthetic geometry properties.
    3. Look-alike honesty rules are strictly enforced:
       - Only low-wind area is assessed when environmental field is present.
       - Natural films, radar artefacts, and sea-state variations are marked NOT assessed.
       - Wind speed >= threshold rules out low-wind calm.
       - Missing environmental field records honest caveat.
    4. Detection confidence travels with its prototype disclaimer note.
    5. Answers keys (demo_origin_expected.json) are NEVER read.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

INTELLIGENCE_DIR = Path(__file__).resolve().parent.parent
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from app.detection import (
    LOOK_ALIKE_CLASSES,
    MODULE_VERSION,
    DemoSatelliteProvider,
    DetectionConfig,
    SatelliteError,
    assess_look_alikes,
    characterise_polygon,
    detect_slick,
    load_demo_slick,
    observe_case,
)
from app.hindcast.environmental import EnvironmentalField

CASE_DIR = INTELLIGENCE_DIR / "data" / "demo" / "case_001"


class TestSatelliteDetection(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = load_demo_slick(CASE_DIR)
        cls.field = EnvironmentalField.load(CASE_DIR / "environmental" / "demo_environmental_field.json")

    def test_load_demo_slick_structure(self) -> None:
        self.assertEqual(self.scenario.get("caseId"), "CASE-001")
        self.assertEqual(self.scenario.get("detectionConfidence"), 0.91)
        self.assertIn("geometry", self.scenario)
        self.assertEqual(self.scenario["geometry"]["type"], "Polygon")

    def test_characterise_polygon(self) -> None:
        char = characterise_polygon(self.scenario)
        self.assertAlmostEqual(char["areaKm2"], 41.258, places=2)
        self.assertAlmostEqual(char["centroid"]["lat"], 18.466, places=2)
        self.assertAlmostEqual(char["centroid"]["lon"], 72.163, places=2)
        self.assertGreater(char["perimeterKm"], 20.0)
        self.assertIn("boundingBox", char)
        self.assertEqual(char["approximateLengthKm"], 12.0)
        self.assertEqual(char["approximateWidthKm"], 4.4)
        self.assertEqual(char["orientationDeg"], 52.0)

    def test_characterise_rejects_malformed_geometry(self) -> None:
        with self.assertRaises(SatelliteError):
            characterise_polygon({})
        with self.assertRaises(SatelliteError):
            characterise_polygon({"geometry": {"type": "Point", "coordinates": [0, 0]}})
        with self.assertRaises(SatelliteError):
            characterise_polygon({"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]}})

    def test_look_alikes_with_field(self) -> None:
        centroid = {"lat": 18.466325, "lon": 72.163105}
        result = assess_look_alikes(centroid, field=self.field)
        self.assertEqual(result["checkedClasses"], ["low wind area"])
        for not_assessed in ["natural or biogenic film", "radar artefact", "sea-state variation"]:
            self.assertIn(not_assessed, result["notAssessedClasses"])
        # Wind is ~8 m/s in demo field, so low wind is NOT suspected
        self.assertFalse(result["lowWindArea"])
        self.assertFalse(result["lookAlikeWarning"])
        self.assertAlmostEqual(result["windSpeedMs"], 8.0, delta=1.0)

    def test_look_alikes_without_field(self) -> None:
        centroid = {"lat": 18.466325, "lon": 72.163105}
        result = assess_look_alikes(centroid, field=None)
        self.assertEqual(result["checkedClasses"], [])
        self.assertIsNone(result["lowWindArea"])
        self.assertIn("not supplied", " ".join(result["notes"]))

    def test_detect_slick_full_pipeline(self) -> None:
        res = detect_slick(self.scenario, field=self.field)
        self.assertEqual(res["module"], "detection")
        self.assertEqual(res["moduleVersion"], MODULE_VERSION)
        self.assertTrue(res["detected"])
        self.assertTrue(res["synthetic"])
        self.assertEqual(res["detectionConfidence"], 0.91)
        self.assertIn("Prototype confidence", res["detectionConfidenceNote"])
        self.assertFalse(res["lookAlikeWarning"])

    def test_observe_case_for_case_001(self) -> None:
        res = observe_case(CASE_DIR)
        self.assertIn("dataSource", res)
        self.assertIn("DemoSatelliteProvider", res["dataSource"])
        self.assertEqual(res["caseId"], "CASE-001")
        self.assertEqual(res["spillId"], "SPILL-001")
        self.assertIn("characterisation", res)
        self.assertIn("lookAlikeAssessment", res)
        self.assertTrue(res["meetsConfidenceThreshold"])

    def test_confidence_below_threshold_triggers_warning(self) -> None:
        scen = copy.deepcopy(self.scenario)
        scen["detectionConfidence"] = 0.4
        res = detect_slick(scen, field=self.field, config=DetectionConfig(min_confidence=0.5))
        self.assertFalse(res["meetsConfidenceThreshold"])
        self.assertTrue(any("below prototype threshold" in w for w in res["warnings"]))

    def test_answer_key_never_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            import shutil
            shutil.copy(CASE_DIR / "demo_slick.json", tmp_path / "demo_slick.json")
            res = observe_case(tmp_path)
            self.assertTrue(res["detected"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
