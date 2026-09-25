#!/usr/bin/env python3
"""ABYSS - Unit tests for Phase 19 normalized ingestion contracts and validation.

PROVES:
    1. Dataclasses correctly format and serialize contracts without core mutation.
    2. Boundary adapters cleanly ingest real CASE-001 demo files.
    3. Strict validation behavior (structural errors reject, sentinels drop to None).
    4. Round-trip and lossless hand-off to downstream core modules.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

INTELLIGENCE_DIR = Path(__file__).resolve().parent.parent
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from app.ingestion import (
    CONTRACT_VERSION,
    ERROR,
    WARNING,
    AisAdapter,
    AisReport,
    EnvironmentalAdapter,
    EnvironmentalObservation,
    NormalizedBatch,
    Provenance,
    SatelliteAdapter,
    SatelliteObservation,
    ingest_ais_csv,
    ingest_environmental_json,
    ingest_satellite_scenario,
    normalize_batch,
    validate_ais_report,
    validate_environmental_observation,
    validate_satellite_observation,
)


class TestIngestionContracts(unittest.TestCase):
    """Test contract dataclass behavior and serialization."""

    def test_provenance_round_trip(self):
        raw = {
            "sourceType": "test_src",
            "sourceName": "Test Provider",
            "sourceFile": "/path/to/test.csv",
            "synthetic": True,
            "datasetLabel": "Demo Dataset",
        }
        p = Provenance.from_dict(raw)
        self.assertEqual(p.sourceType, "test_src")
        self.assertTrue(p.synthetic)
        self.assertEqual(p.to_dict()["datasetLabel"], "Demo Dataset")

    def test_satellite_contract_handoff(self):
        obs = SatelliteObservation(
            acquisitionTime="2026-03-14T06:00:00Z",
            geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            centroid={"lat": 0.5, "lon": 0.5},
            detectionConfidence=0.9,
            spillId="SPILL-01",
            characteristics={"areaKm2": 12.5},
            provenance=Provenance(sourceType="satellite", synthetic=True),
        )
        scenario = obs.to_detection_scenario()
        self.assertEqual(scenario["acquisitionTime"], "2026-03-14T06:00:00Z")
        self.assertEqual(scenario["spillId"], "SPILL-01")
        self.assertEqual(scenario["areaKm2"], 12.5)
        self.assertTrue(scenario["synthetic"])

    def test_ais_contract_handoff(self):
        rep = AisReport(
            mmsi="900000001",
            timestamp="2026-03-14T10:00:00Z",
            latitude=18.5,
            longitude=72.5,
            sogKn=12.4,
            cogDeg=180.0,
            provenance=Provenance(sourceType="ais", synthetic=True, datasetLabel="Demo"),
        )
        rec = rep.to_core_record()
        self.assertEqual(rec["mmsi"], "900000001")
        self.assertEqual(rec["sogKn"], 12.4)
        self.assertTrue(rec["synthetic"])
        self.assertEqual(rec["datasetLabel"], "Demo")

    def test_environmental_contract_handoff(self):
        env = EnvironmentalObservation(
            timestamp="2026-03-14T06:00:00Z",
            latitude=18.0,
            longitude=72.0,
            uCurrent=0.25,
            vCurrent=-0.15,
            windSpeedMs=5.0,
            windFromDirectionDeg=270.0,
        )
        node = env.to_field_node()
        self.assertEqual(node["lat"], 18.0)
        self.assertEqual(node["lon"], 72.0)
        self.assertEqual(node["uCurrent"], 0.25)
        self.assertEqual(node["windSpeed"], 5.0)


class TestIngestionValidation(unittest.TestCase):
    """Test validation rules, error recording, and warning sentinels."""

    def test_satellite_validation_missing_fields(self):
        raw = {"spillId": "S1"}
        obs, issues = validate_satellite_observation(raw)
        self.assertIsNone(obs)
        errors = [i for i in issues if i.severity == ERROR]
        self.assertTrue(any(i.field == "acquisitionTime" for i in errors))
        self.assertTrue(any(i.field == "geometry" for i in errors))
        self.assertTrue(any(i.field == "centroid" for i in errors))

    def test_ais_sentinel_handling(self):
        raw = {
            "mmsi": "900000002",
            "timestamp": "2026-03-14T12:00:00Z",
            "latitude": 19.0,
            "longitude": 73.0,
            "sogKn": 102.3,   # Sentinel
            "cogDeg": 360.0,   # Sentinel
            "headingDeg": 511, # Sentinel
        }
        rep, issues = validate_ais_report(raw)
        self.assertIsNotNone(rep)
        self.assertIsNone(rep.sogKn)
        self.assertIsNone(rep.cogDeg)
        self.assertIsNone(rep.headingDeg)
        warnings = [i for i in issues if i.severity == WARNING]
        self.assertEqual(len(warnings), 3)

    def test_ais_invalid_mmsi_and_coordinates(self):
        raw = {
            "mmsi": "123",  # Not 9 digits
            "timestamp": "2026-03-14T12:00:00Z",
            "latitude": 105.0,  # Out of range [-90, 90]
            "longitude": 73.0,
        }
        rep, issues = validate_ais_report(raw)
        self.assertIsNone(rep)
        errors = [i for i in issues if i.severity == ERROR]
        self.assertTrue(any(i.code == "invalid_mmsi" for i in errors))
        self.assertTrue(any(i.code == "out_of_range" for i in issues))

    def test_normalize_batch_aggregation(self):
        records = [
            {"mmsi": "900000001", "timestamp": "2026-03-14T10:00:00Z", "latitude": 18.0, "longitude": 72.0},
            {"mmsi": "bad_mmsi", "timestamp": "2026-03-14T10:00:00Z", "latitude": 18.0, "longitude": 72.0},
        ]
        batch = normalize_batch("ais", records)
        self.assertEqual(batch.accepted, 1)
        self.assertEqual(batch.rejected, 1)
        self.assertEqual(len(batch.records), 1)
        self.assertEqual(batch.records[0].mmsi, "900000001")


class TestDemoAssetIngestion(unittest.TestCase):
    """Test ingesting actual demo assets bundled with CASE-001."""

    def setUp(self):
        self.case_dir = INTELLIGENCE_DIR / "data" / "demo" / "case_001"

    def test_ingest_demo_satellite(self):
        slick_path = self.case_dir / "demo_slick.json"
        if not slick_path.exists():
            self.skipTest("demo_slick.json not present")

        batch = ingest_satellite_scenario(slick_path)
        self.assertEqual(batch.accepted, 1)
        self.assertEqual(batch.rejected, 0)
        obs: SatelliteObservation = batch.records[0]
        self.assertEqual(obs.caseId, "CASE-001")
        self.assertTrue(obs.provenance.synthetic)

    def test_ingest_demo_ais_csv(self):
        ais_path = self.case_dir / "ais" / "demo_ais_positions.csv"
        if not ais_path.exists():
            self.skipTest("demo_ais_positions.csv not present")

        batch = ingest_ais_csv(ais_path)
        self.assertGreater(batch.accepted, 3000)
        self.assertGreater(batch.rejected, 0)
        self.assertTrue(len(batch.issues) > 0)

    def test_ingest_demo_environmental_field(self):
        env_path = self.case_dir / "environmental" / "demo_environmental_field.json"
        if not env_path.exists():
            self.skipTest("demo_environmental_field.json not present")

        batch = ingest_environmental_json(env_path)
        self.assertEqual(batch.rejected, 0)
        self.assertEqual(batch.accepted, 117)
        obs: EnvironmentalObservation = batch.records[0]
        self.assertIsNotNone(obs.windageCoefficient)
        self.assertTrue(obs.provenance.synthetic)


if __name__ == "__main__":
    unittest.main()

