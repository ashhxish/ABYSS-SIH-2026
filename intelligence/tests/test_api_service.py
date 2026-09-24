#!/usr/bin/env python3
"""ABYSS - unit and integration tests for FastAPI intelligence service (Phase 13).

Validates all 12 endpoints with data source provenance and warnings envelopes.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

INTELLIGENCE_DIR = Path(__file__).resolve().parent.parent
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from app.main import app


class TestApiService(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def _assert_envelope(self, resp_data: dict) -> None:
        self.assertIn("dataSource", resp_data)
        self.assertIsInstance(resp_data["dataSource"], str)
        self.assertTrue(len(resp_data["dataSource"]) > 0)
        self.assertIn("warnings", resp_data)
        self.assertIsInstance(resp_data["warnings"], list)

    def test_01_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self._assert_envelope(data)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "abyss-intelligence")
        self.assertEqual(data["dataMode"], "demo")
        self.assertEqual(data["demoCaseId"], "CASE-001")

    def test_02_data_sources(self) -> None:
        response = self.client.get("/data-sources")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self._assert_envelope(data)
        self.assertTrue(data["demo"])
        self.assertGreaterEqual(len(data["sources"]), 3)
        names = [s["name"] for s in data["sources"]]
        self.assertIn("DemoSatelliteProvider", names)
        self.assertIn("DemoAISProvider", names)
        self.assertIn("DemoEnvironmentalProvider", names)

    def test_03_detect(self) -> None:
        response = self.client.post("/detect")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self._assert_envelope(data)
        det = data["detection"]
        self.assertTrue(det["detected"])
        self.assertEqual(det["classification"], "possible oil slick (dark formation candidate)")
        self.assertEqual(det["detectionConfidence"], 0.91)
        self.assertIn("characterisation", det)
        self.assertIn("lookAlikeAssessment", det)

    def test_04_characterize(self) -> None:
        response = self.client.post("/characterize")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self._assert_envelope(data)
        char = data["characterisation"]
        self.assertAlmostEqual(char["areaKm2"], 41.258, places=2)
        self.assertAlmostEqual(char["centroid"]["lat"], 18.466, places=2)
        self.assertGreater(char["perimeterKm"], 20.0)
        self.assertIn("boundingBox", char)

    def test_05_hindcast(self) -> None:
        response = self.client.post("/hindcast")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self._assert_envelope(data)
        origin = data["origin"]
        # The result is a REGION (no point estimate) with its provenance attached.
        self.assertEqual(origin["region"]["method"].split()[0], "backward")
        self.assertGreaterEqual(origin["region"]["vertexCount"], 4)
        self.assertGreater(origin["region"]["areaKm2"], 0.0)
        self.assertNotIn("centroid", origin["region"])
        self.assertGreater(origin["sampleCount"], 0)
        self.assertGreater(origin["seedCount"], 0)
        self.assertIn("confidence", origin["region"])
        self.assertIn("releaseWindow", origin)
        self.assertIn("observedAt", origin)

    def test_06_ais_clean(self) -> None:
        resp1 = self.client.post("/ais/clean", json={"includeRecords": False})
        self.assertEqual(resp1.status_code, 200)
        d1 = resp1.json()
        self._assert_envelope(d1)
        self.assertEqual(d1["cleaning"]["statistics"]["counts"]["records"], 3666)
        self.assertEqual(len(d1["cleaning"]["records"]), 0)
        self.assertTrue(any("omitted" in w for w in d1["warnings"]))

        resp2 = self.client.post("/ais/clean", json={"includeRecords": True})
        self.assertEqual(resp2.status_code, 200)
        d2 = resp2.json()
        self.assertGreater(len(d2["cleaning"]["records"]), 0)

    def test_07_ais_trajectory(self) -> None:
        response = self.client.post("/ais/trajectory")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self._assert_envelope(data)
        traj = data["trajectories"]
        self.assertEqual(traj["module"], "ais.trajectory")
        self.assertEqual(traj["statistics"]["counts"]["vessels"], 12)

    def test_08_ais_filter(self) -> None:
        response = self.client.post("/ais/filter")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self._assert_envelope(data)
        flt = data["filter"]
        self.assertEqual(flt["vesselCount"], 12)
        self.assertGreaterEqual(flt["candidatesPassingSpatial"], 1)

    def test_09_ais_behaviour(self) -> None:
        response = self.client.post("/ais/behaviour")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self._assert_envelope(data)
        beh = data["behaviour"]
        self.assertEqual(beh["vesselCount"], 12)

    def test_10_ais_gaps(self) -> None:
        response = self.client.post("/ais/gaps")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self._assert_envelope(data)
        gaps = data["gaps"]
        self.assertEqual(gaps["vesselCount"], 12)

    def test_11_score_and_weights(self) -> None:
        resp = self.client.post("/score")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self._assert_envelope(data)
        scoring = data["scoring"]
        self.assertIn("ranking", scoring)
        self.assertEqual(len(scoring["ranking"]["entries"]), 12)

        resp_wt = self.client.post("/score", json={"weights": {"spatial": 0.5, "gap": 0.5}})
        self.assertEqual(resp_wt.status_code, 200)
        d_wt = resp_wt.json()
        self.assertEqual(d_wt["scoring"]["weights"]["spatial"], 0.5)

        resp_bad = self.client.post("/score", json={"weights": {"spatial": -1.0}})
        self.assertEqual(resp_bad.status_code, 422)

        # Unknown factor names are rejected loudly (never silently ignored)
        resp_typo = self.client.post("/score", json={"weights": {"spaital": 10.0}})
        self.assertEqual(resp_typo.status_code, 400)

    def test_12_investigate(self) -> None:
        response = self.client.post("/investigate")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self._assert_envelope(data)
        inv = data["investigation"]
        self.assertEqual(inv["caseId"], "CASE-001")
        self.assertEqual(inv["statistics"]["vesselsScored"], 12)
        self.assertEqual(inv["ranking"]["entries"][0]["mmsi"], "900000001")


if __name__ == "__main__":
    unittest.main(verbosity=2)
