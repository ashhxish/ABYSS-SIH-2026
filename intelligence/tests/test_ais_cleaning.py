#!/usr/bin/env python3
"""ABYSS - Phase 3 tests for AIS ingestion and cleaning.

WHAT THESE TESTS PROVE
    1. the bundled synthetic CASE-001 extract cleans to exactly the numbers the
       Phase 2 defect inventory promises (3,669 rows in, 3,660 records out,
       9 rejections split 4 duplicates / 2 malformed timestamps / 2 invalid
       coordinates / 1 impossible speed, plus 1 removed value and 3 warnings)
    2. nothing is dropped silently: accepted + rejected == input, and every rejected
       row and removed value carries a source line, a category, a reason and its raw
       values
    3. the documented edge cases behave correctly: blank fields, non-numeric and
       out-of-range coordinates, null island, malformed timestamps, naive and
       offset timestamps, duplicate and conflicting records, AIS 'not available'
       sentinels, invalid IMO and vessel type, and a configurable impossible-speed
       threshold
    4. cleaning is deterministic and its output is JSON-serialisable

WHAT THESE TESTS DO NOT DO
    No trajectory construction, no gap detection, no spatial/temporal/trajectory
    filtering, no behaviour analysis and no scoring. Those belong to later phases.

RUN (needs the project virtual environment because pandas is required)
    .venv/bin/python -m unittest discover -s intelligence/tests -v
    .venv/bin/python intelligence/tests/test_ais_cleaning.py -v
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

INTELLIGENCE_DIR = Path(__file__).resolve().parent.parent
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from app import config as app_config
from app.ais import cleaning
from app.ais.cleaning import (
    CleaningConfig,
    AisIngestionError,
    REJECT_DUPLICATE,
    REJECT_IMPOSSIBLE_SPEED,
    REJECT_INVALID_COORDINATE,
    REJECT_INVALID_IDENTIFIER,
    REJECT_MALFORMED_TIMESTAMP,
    REJECT_MISSING_IDENTIFIER,
    REJECT_MISSING_REQUIRED_FIELD,
    REMOVE_INVALID_SPEED,
    REMOVE_NOT_AVAILABLE,
    WARN_ASSUMED_UTC,
    WARN_CONFLICTING_TIMESTAMP,
    WARN_INVALID_IMO,
    WARN_MISSING_OPTIONAL,
    WARN_UNKNOWN_VESSEL_TYPE,
)

DATASET_LABEL = "Synthetic Demonstration Dataset"
EXPECTED_MMSI = {f"V{i:03d}": f"9000000{i:02d}" for i in range(1, 13)}

# Numbers fixed by the Phase 2 defect inventory (intelligence/data/demo/case_001/README.md),
# repeated here on purpose so a change in the generator cannot quietly change cleaning.
DEMO_ROWS_IN = 3675
DEMO_RECORDS = 3666
DEMO_REJECTED = 9
DEMO_REJECTIONS = {
    REJECT_DUPLICATE: 4,
    REJECT_MALFORMED_TIMESTAMP: 2,
    REJECT_INVALID_COORDINATE: 2,
    REJECT_IMPOSSIBLE_SPEED: 1,
}
DEMO_REJECTIONS_BY_VESSEL = {"V006": 1, "V007": 4, "V008": 2, "V010": 1, "V012": 1}

HEADER = [
    "MMSI", "IMO", "vesselName", "vesselType", "timestamp", "latitude", "longitude",
    "SOG", "COG", "heading", "navigationStatus", "datasetLabel",
]


def row(
    mmsi: str = "900000001", ts: str = "2026-03-11T06:00:00Z", lat: str = "18.000000",
    lon: str = "72.000000", sog: str = "10.0", cog: str = "90.0", heading: str = "90",
    nav: str = "0", name: str = "DEMO TEST", imo: str = "9990014", vtype: str = "70",
    label: str = DATASET_LABEL,
) -> list:
    return [mmsi, imo, name, vtype, ts, lat, lon, sog, cog, heading, nav, label]


def write_csv(path: Path, rows: list, header: list | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header or HEADER)
        writer.writerows(rows)
    return path


def clean_rows(rows: list, config: CleaningConfig | None = None, header: list | None = None):
    """Clean a crafted CSV in a temporary directory, keeping only plain Python objects."""
    with tempfile.TemporaryDirectory(prefix="abyss_cleaning_") as tmp:
        path = write_csv(Path(tmp) / "ais.csv", rows, header)
        return cleaning.clean_csv(path, config)


class TestDemoDatasetCleaning(unittest.TestCase):
    """Cleaning the bundled synthetic CASE-001 extract must match the documented inventory."""

    @classmethod
    def setUpClass(cls):
        cls.result = cleaning.clean_demo_case()

    def test_counts_match_the_documented_defect_inventory(self):
        counts = self.result.statistics["counts"]
        self.assertEqual(counts["rowsIn"], DEMO_ROWS_IN)
        self.assertEqual(counts["records"], DEMO_RECORDS)
        self.assertEqual(counts["rowsRejected"], DEMO_REJECTED)
        self.assertEqual(counts["vessels"], 12)
        self.assertEqual(self.result.statistics["rejectionByCategory"], dict(sorted(DEMO_REJECTIONS.items())))
        self.assertEqual(counts["valuesRemoved"], 1)
        self.assertEqual(counts["rowsWithRemovedValues"], 1)
        self.assertEqual(counts["rowsWithWarnings"], 4,
                         "3 rows missing optional fields + 1 row that lost an impossible value")
        self.assertEqual(self.result.statistics["warningByCategory"],
                         {WARN_MISSING_OPTIONAL: 3, REMOVE_INVALID_SPEED: 1})

    def test_nothing_is_dropped_silently(self):
        counts = self.result.statistics["counts"]
        self.assertEqual(counts["records"] + counts["rowsRejected"], counts["rowsIn"])
        self.assertEqual(len(self.result.rejected), counts["rowsRejected"])
        for entry in self.result.rejected:
            self.assertGreater(entry["sourceLine"], 1)
            self.assertTrue(entry["category"])
            self.assertTrue(entry["reason"])
            self.assertTrue(entry["rawValues"], "a rejected row must keep its raw values")
            self.assertIn(entry["category"], cleaning.REJECTION_CATEGORIES)
        audit_lines = {entry["sourceLine"] for entry in self.result.rejected}
        record_lines = {record["sourceLine"] for record in self.result.records}
        self.assertFalse(audit_lines & record_lines, "a rejected row must not also appear as a record")

    def test_rejections_are_attributed_to_the_intended_vessels(self):
        by_vessel = self.result.statistics["rejectionByVessel"]
        expected = {EXPECTED_MMSI[vessel]: count for vessel, count in DEMO_REJECTIONS_BY_VESSEL.items()}
        self.assertEqual(by_vessel, dict(sorted(expected.items())))

    def test_rejected_rows_identify_the_documented_values(self):
        reasons: dict = {}
        for entry in self.result.rejected:
            reasons[entry["category"]] = reasons.get(entry["category"], "") + " | " + entry["reason"]
        self.assertIn("2026-03-12T25:61:00Z", reasons[REJECT_MALFORMED_TIMESTAMP])
        self.assertIn("12/03/2026 08:00", reasons[REJECT_MALFORMED_TIMESTAMP])
        self.assertIn("null-island", reasons[REJECT_INVALID_COORDINATE])
        self.assertIn("95.2", reasons[REJECT_INVALID_COORDINATE])
        self.assertIn("389.2", reasons[REJECT_IMPOSSIBLE_SPEED])
        self.assertIn("max_plausible_speed_kn=60.0", reasons[REJECT_IMPOSSIBLE_SPEED])

    def test_only_one_row_is_rejected_for_the_single_injected_teleport(self):
        """The injected bad record creates two impossible steps; only the bad row may go."""
        entries = [entry for entry in self.result.rejected if entry["category"] == REJECT_IMPOSSIBLE_SPEED]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["vesselIdentifier"], EXPECTED_MMSI["V006"])
        rejected_line = entries[0]["sourceLine"]
        from app.geo import haversine_km, implied_speed_kn

        v006 = [record for record in self.result.records if record["mmsi"] == EXPECTED_MMSI["V006"]]
        before = [record for record in v006 if record["sourceLine"] < rejected_line]
        after = [record for record in v006 if record["sourceLine"] > rejected_line]
        self.assertTrue(before and after, "records either side of the teleport must survive")
        previous = max(before, key=lambda record: record["sourceLine"])
        successor = min(after, key=lambda record: record["sourceLine"])
        distance = haversine_km(previous["latitude"], previous["longitude"],
                                successor["latitude"], successor["longitude"])
        speed = implied_speed_kn(distance, successor["epochSeconds"] - previous["epochSeconds"])
        self.assertIsNotNone(speed)
        self.assertLessEqual(speed, 60.0,
                             "the successor record must be reachable from the previous accepted record")

    def test_negative_speed_value_is_removed_but_the_row_is_kept(self):
        self.assertEqual(len(self.result.removed_values), 1)
        entry = self.result.removed_values[0]
        self.assertEqual(entry["category"], REMOVE_INVALID_SPEED)
        self.assertEqual(entry["rawValue"], "-3.0")
        self.assertEqual(entry["vesselIdentifier"], EXPECTED_MMSI["V006"])
        record = next(r for r in self.result.records if r["sourceLine"] == entry["sourceLine"])
        self.assertIsNone(record["sogKn"], "an impossible value must not survive as a number")
        self.assertIn(REMOVE_INVALID_SPEED, record["warnings"])

    def test_missing_optional_fields_warn_rather_than_reject(self):
        affected = [r for r in self.result.records if WARN_MISSING_OPTIONAL in r["warnings"]]
        self.assertEqual(len(affected), 3)
        for record in affected:
            self.assertEqual(record["mmsi"], EXPECTED_MMSI["V011"])
            self.assertIsNone(record["headingDeg"])
            self.assertIsNone(record["navigationStatus"])
            self.assertIsNotNone(record["latitude"], "position must still be usable")

    def test_records_are_normalised_and_carry_provenance(self):
        vessel_ids = {record["mmsi"] for record in self.result.records}
        self.assertEqual(vessel_ids, set(EXPECTED_MMSI.values()))
        for record in self.result.records:
            self.assertRegex(record["timestamp"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            self.assertIsInstance(record["epochSeconds"], int)
            self.assertTrue(-90.0 <= record["latitude"] <= 90.0)
            self.assertTrue(-180.0 <= record["longitude"] <= 180.0)
            self.assertTrue(record["synthetic"], "demo records must stay labelled synthetic")
            self.assertEqual(record["datasetLabel"], DATASET_LABEL)
            self.assertGreater(record["sourceLine"], 1)
            if record["sogKn"] is not None:
                self.assertGreaterEqual(record["sogKn"], 0.0)
            if record["cogDeg"] is not None:
                self.assertTrue(0.0 <= record["cogDeg"] < 360.0)
            if record["headingDeg"] is not None:
                self.assertTrue(0 <= record["headingDeg"] <= 359)

    def test_records_are_time_ordered(self):
        seconds = [record["epochSeconds"] for record in self.result.records]
        self.assertEqual(seconds, sorted(seconds))
        counts = self.result.statistics["counts"]
        self.assertEqual(counts["rowsReordered"], 0,
                         "the Phase 2 extract is already time-ordered")

    def test_time_range_and_reporting_interval_are_reported(self):
        time_range = self.result.statistics["timeRange"]
        self.assertEqual(time_range["start"], "2026-03-11T06:00:00Z")
        self.assertEqual(time_range["end"], "2026-03-14T05:55:00Z")
        interval = self.result.statistics["reportingIntervalSeconds"]
        self.assertEqual(interval["modalSeconds"], 300)
        self.assertIn("not gap analysis", interval["note"])

    def test_vessel_summaries_cover_every_vessel(self):
        self.assertEqual(len(self.result.vessels), 12)
        total = sum(vessel["records"] for vessel in self.result.vessels)
        self.assertEqual(total, len(self.result.records))
        for vessel in self.result.vessels:
            self.assertRegex(vessel["mmsi"], r"^9000000\d{2}$")
            self.assertLessEqual(vessel["firstTimestamp"], vessel["lastTimestamp"])

    def test_synthetic_provenance_is_flagged_for_the_ui(self):
        self.assertTrue(self.result.synthetic)
        self.assertEqual(self.result.data_source, "DemoAISProvider")
        self.assertTrue(any("Synthetic Demonstration Dataset" in w for w in self.result.warnings),
                        "the UI label for synthetic AIS must be present")
        payload = self.result.to_dict()
        self.assertTrue(payload["synthetic"])
        self.assertIn(DATASET_LABEL, payload["datasetLabels"])

    def test_cleaning_is_deterministic(self):
        first = cleaning.clean_demo_case().to_dict()
        second = cleaning.clean_demo_case().to_dict()
        self.assertEqual(first, second)

    def test_result_is_json_serialisable_and_report_ready(self):
        payload = self.result.to_dict()
        payload["summary"] = cleaning.summarise_for_report(self.result)
        encoded = json.dumps(payload)
        self.assertGreater(len(encoded), 1000)
        summary = payload["summary"]
        self.assertEqual(summary["rowsIn"], DEMO_ROWS_IN)
        self.assertEqual(summary["rowsOut"], DEMO_RECORDS)
        self.assertIn("notes", summary)
        self.assertIn("synthetic", summary)
        self.assertFalse(summary["synthetic"] is None)

    def test_notes_state_the_audit_and_prototype_threshold(self):
        text = " ".join(self.result.notes)
        self.assertIn("never deletes a suspicious record", text)
        self.assertIn("PROTOTYPE", text)
        self.assertIn("max_plausible_speed_kn=60.0", text)


class TestCleaningEdgeCases(unittest.TestCase):
    """Crafted inputs for documented edge cases the demo extract does not contain."""

    def test_blank_required_fields_are_rejected_with_per_field_reasons(self):
        result = clean_rows([row(ts=""), row(lat=""), row(lon="")])
        self.assertEqual(result.statistics["counts"]["rowsIn"], 3)
        self.assertEqual(result.statistics["counts"]["records"], 0)
        reasons = " | ".join(entry["reason"] for entry in result.rejected)
        self.assertIn("blank timestamp", reasons)
        self.assertIn("blank latitude", reasons)
        self.assertIn("blank longitude", reasons)
        self.assertEqual({entry["category"] for entry in result.rejected}, {REJECT_MISSING_REQUIRED_FIELD})

    def test_non_numeric_coordinates_are_rejected(self):
        result = clean_rows([row(lat="not-a-number"), row(lon="--")])
        self.assertEqual(result.statistics["counts"]["records"], 0)
        self.assertEqual({entry["category"] for entry in result.rejected}, {REJECT_INVALID_COORDINATE})
        for entry in result.rejected:
            self.assertIn("not numeric", entry["reason"])

    def test_out_of_range_and_null_island_coordinates_are_rejected(self):
        result = clean_rows([row(lat="95.2"), row(lon="-181.0"), row(lat="0.0", lon="0.0")])
        self.assertEqual(result.statistics["counts"]["records"], 0)
        reasons = " | ".join(entry["reason"] for entry in result.rejected)
        self.assertIn("latitude out of range: 95.2", reasons)
        self.assertIn("longitude out of range: -181.0", reasons)
        self.assertIn("null-island", reasons)

    def test_missing_and_invalid_identifiers_are_distinguished(self):
        result = clean_rows([row(mmsi=""), row(mmsi="12345"), row(mmsi="ABCDEFGHI")])
        categories = [entry["category"] for entry in result.rejected]
        self.assertIn(REJECT_MISSING_IDENTIFIER, categories)
        self.assertEqual(categories.count(REJECT_INVALID_IDENTIFIER), 2)
        self.assertEqual(result.statistics["counts"]["records"], 0)

    def test_malformed_timestamps_are_rejected_and_offset_timestamps_are_converted(self):
        result = clean_rows([
            row(ts="12/03/2026 08:00"),
            row(ts="2026-13-01T00:00:00Z"),
            row(ts="2026-03-11T08:00:00+02:00"),
        ])
        self.assertEqual(result.statistics["counts"]["records"], 1)
        self.assertEqual(result.statistics["counts"]["rowsRejected"], 2)
        self.assertEqual(result.records[0]["timestamp"], "2026-03-11T06:00:00Z")

    def test_naive_and_space_separated_timestamps_are_treated_as_utc_with_a_warning(self):
        result = clean_rows([row(ts="2026-03-11T06:00:00"), row(ts="2026-03-11 06:05:00")])
        self.assertEqual(result.statistics["counts"]["records"], 2)
        self.assertEqual(result.records[0]["timestamp"], "2026-03-11T06:00:00Z")
        self.assertEqual(result.records[1]["timestamp"], "2026-03-11T06:05:00Z")
        self.assertEqual(result.statistics["warningByCategory"][WARN_ASSUMED_UTC], 2)

    def test_exact_duplicates_are_rejected_with_a_reference_to_the_original(self):
        duplicate = row()
        result = clean_rows([duplicate, duplicate, row(ts="2026-03-11T06:05:00Z")])
        self.assertEqual(result.statistics["counts"]["records"], 2)
        self.assertEqual(result.statistics["counts"]["rowsRejected"], 1)
        entry = result.rejected[0]
        self.assertEqual(entry["category"], REJECT_DUPLICATE)
        self.assertIn("source line 2", entry["reason"])

    def test_conflicting_positions_sharing_one_timestamp_are_kept_and_warned(self):
        result = clean_rows([row(lat="18.0", lon="72.0"), row(lat="18.5", lon="72.5")])
        self.assertEqual(result.statistics["counts"]["records"], 2)
        self.assertEqual(result.statistics["counts"]["rowsRejected"], 0,
                         "speed cannot be inferred from one timestamp, so neither row may be deleted")
        self.assertEqual(result.statistics["warningByCategory"][WARN_CONFLICTING_TIMESTAMP], 2)
        for record in result.records:
            self.assertIn(WARN_CONFLICTING_TIMESTAMP, record["warnings"])

    def test_impossible_speed_threshold_is_configurable(self):
        rows = [
            row(ts="2026-03-11T06:00:00Z", lat="18.0", lon="72.0"),
            row(ts="2026-03-11T06:30:00Z", lat="18.54", lon="72.0"),  # ~60 km in 30 minutes (~65 kn)
        ]
        strict = clean_rows(rows)
        self.assertEqual(strict.statistics["counts"]["rowsRejected"], 1)
        self.assertEqual(strict.rejected[0]["category"], REJECT_IMPOSSIBLE_SPEED)
        self.assertIn("implied speed", strict.rejected[0]["reason"])
        lenient = clean_rows(rows, CleaningConfig(max_plausible_speed_kn=200.0))
        self.assertEqual(lenient.statistics["counts"]["rowsRejected"], 0)
        self.assertEqual(lenient.statistics["counts"]["records"], 2)

    def test_not_available_sentinels_are_nulled_by_default(self):
        result = clean_rows([row(sog="102.3", cog="360.0", heading="511")])
        record = result.records[0]
        self.assertIsNone(record["sogKn"])
        self.assertIsNone(record["cogDeg"])
        self.assertIsNone(record["headingDeg"])
        self.assertIn(REMOVE_NOT_AVAILABLE, {entry["category"] for entry in result.removed_values})
        self.assertEqual(result.statistics["counts"]["records"], 1)

    def test_sentinel_handling_can_be_disabled(self):
        result = clean_rows([row(sog="102.3", cog="360.0", heading="511")],
                            CleaningConfig(treat_not_available_sentinels=False))
        record = result.records[0]
        self.assertAlmostEqual(record["sogKn"], 102.3)
        self.assertIsNone(record["cogDeg"], "360 degrees is out of range whatever the sentinel setting")
        self.assertIsNone(record["headingDeg"])

    def test_invalid_imo_and_unrecognised_vessel_type_are_warnings_only(self):
        result = clean_rows([row(imo="123", vtype="not-a-code")])
        record = result.records[0]
        self.assertEqual(result.statistics["counts"]["rowsRejected"], 0)
        self.assertIn(WARN_INVALID_IMO, record["warnings"])
        self.assertIn(WARN_UNKNOWN_VESSEL_TYPE, record["warnings"])
        self.assertIsNone(record["vesselType"])

    def test_audit_line_numbers_point_at_the_source_row(self):
        rows = [row(), row(ts="2026-03-11T06:05:00Z"),
                row(ts="12/03/2026 08:00"), row(ts="2026-03-11T06:15:00Z")]
        result = clean_rows(rows)
        self.assertEqual(len(result.rejected), 1)
        self.assertEqual(result.rejected[0]["sourceLine"], 4)
        self.assertEqual(result.rejected[0]["rawValues"]["timestamp"], "12/03/2026 08:00")

    def test_unsorted_input_is_sorted_and_reported(self):
        rows = [row(ts="2026-03-11T06:10:00Z"), row(ts="2026-03-11T06:00:00Z"), row(ts="2026-03-11T06:05:00Z")]
        result = clean_rows(rows)
        self.assertEqual([record["timestamp"] for record in result.records],
                         ["2026-03-11T06:00:00Z", "2026-03-11T06:05:00Z", "2026-03-11T06:10:00Z"])
        self.assertGreater(result.statistics["counts"]["rowsReordered"], 0)

    def test_optional_columns_may_be_absent(self):
        result = clean_rows(
            [["900000001", "2026-03-11T06:00:00Z", "18.000000", "72.000000"]],
            header=["MMSI", "timestamp", "latitude", "longitude"],
        )
        self.assertEqual(result.statistics["counts"]["records"], 1)
        self.assertIn(WARN_MISSING_OPTIONAL, result.records[0]["warnings"])

    def test_missing_required_column_is_a_clear_error(self):
        with tempfile.TemporaryDirectory(prefix="abyss_cleaning_") as tmp:
            path = write_csv(Path(tmp) / "bad.csv", [["900000001", "2026-03-11T06:00:00Z", "72.000000"]],
                             ["MMSI", "timestamp", "longitude"])
            with self.assertRaises(AisIngestionError) as context:
                cleaning.clean_csv(path)
        self.assertIn("latitude", str(context.exception))

    def test_empty_file_and_missing_file_are_clear_errors(self):
        with tempfile.TemporaryDirectory(prefix="abyss_cleaning_") as tmp:
            empty = Path(tmp) / "empty.csv"
            empty.write_text(",".join(HEADER) + "\n", encoding="utf-8")
            with self.assertRaises(AisIngestionError):
                cleaning.read_ais_csv(empty)
            with self.assertRaises(AisIngestionError):
                cleaning.read_ais_csv(Path(tmp) / "does-not-exist.csv")

    def test_cleaned_csv_export_round_trips(self):
        result = clean_rows([row(), row(ts="2026-03-11T06:05:00Z")])
        with tempfile.TemporaryDirectory(prefix="abyss_cleaning_") as tmp:
            out = Path(tmp) / "nested" / "clean.csv"
            cleaning.write_cleaned_csv(out, result.records)
            with out.open(newline="", encoding="utf-8") as handle:
                exported = list(csv.DictReader(handle))
        self.assertEqual(len(exported), 2)
        self.assertEqual(list(exported[0].keys()), list(cleaning.CLEANED_COLUMNS))
        self.assertEqual(exported[0]["timestamp"], "2026-03-11T06:00:00Z")
        self.assertEqual(exported[0]["sourceLine"], "2")

    def test_source_provenance_is_inferred_from_the_data(self):
        labelled = clean_rows([row()])
        self.assertTrue(labelled.synthetic)
        unlabelled = clean_rows([row(label="")])
        self.assertFalse(unlabelled.synthetic)
        self.assertTrue(any("not marked as synthetic" in warning for warning in unlabelled.warnings))


class TestConfiguration(unittest.TestCase):
    """Configuration is environment-driven and must fail loudly when invalid."""

    def test_defaults_are_demo_mode_and_safe(self):
        settings = app_config.get_settings({})
        self.assertEqual(settings.data_mode, "demo")
        self.assertTrue(settings.is_demo_mode)
        self.assertEqual(settings.ais_max_plausible_speed_kn, 60.0)
        self.assertEqual(settings.demo_case_id, "CASE-001")
        self.assertEqual(settings.demo_case_slug, "case_001")
        self.assertEqual(settings.demo_ais_csv,
                         settings.demo_case_dir / "ais" / "demo_ais_positions.csv")

    def test_demo_paths_point_at_the_committed_dataset(self):
        settings = app_config.get_settings({})
        self.assertTrue(settings.demo_ais_csv.exists(), f"missing {settings.demo_ais_csv}")
        self.assertEqual(settings.validate_paths(), [])

    def test_environment_overrides_are_applied_and_normalised(self):
        settings = app_config.get_settings({
            "ABYSS_DATA_MODE": "LIVE",
            "ABYSS_AIS_MAX_PLAUSIBLE_SPEED_KN": "45",
            "ABYSS_DEMO_CASE_ID": "case-007",
            "INTELLIGENCE_LOG_LEVEL": "debug",
            "INTELLIGENCE_PORT": "8123",
        })
        self.assertEqual(settings.data_mode, "live")
        self.assertEqual(settings.ais_max_plausible_speed_kn, 45.0)
        self.assertEqual(settings.demo_case_id, "CASE-007")
        self.assertEqual(settings.demo_case_slug, "case_007")
        self.assertEqual(settings.log_level, "DEBUG")
        self.assertEqual(settings.intelligence_port, 8123)
        self.assertIn("demoCaseSlug", settings.describe())

    def test_invalid_environment_values_fail_loudly(self):
        for environment in (
            {"ABYSS_DATA_MODE": "production"},
            {"ABYSS_AIS_MAX_PLAUSIBLE_SPEED_KN": "fast"},
            {"ABYSS_AIS_MAX_PLAUSIBLE_SPEED_KN": "5000"},
            {"ABYSS_DEMO_CASE_ID": "demo"},
            {"INTELLIGENCE_LOG_LEVEL": "LOUD"},
            {"INTELLIGENCE_PORT": "99999"},
        ):
            with self.assertRaises(app_config.ConfigurationError):
                app_config.get_settings(environment)

    def test_settings_build_a_cleaning_config(self):
        config = app_config.get_settings({}).ais_cleaning_config()
        self.assertIsInstance(config, CleaningConfig)
        self.assertEqual(config.max_plausible_speed_kn, 60.0)

    def test_cleaning_config_validates_its_thresholds(self):
        with self.assertRaises(ValueError):
            CleaningConfig(max_plausible_speed_kn=0.0)
        with self.assertRaises(ValueError):
            CleaningConfig(max_plausible_speed_kn=500.0)
        with self.assertRaises(ValueError):
            CleaningConfig(null_island_tolerance_deg=-1.0)
        with self.assertRaises(ValueError):
            CleaningConfig(max_audit_records=0)

    def test_cleaning_config_is_reported_in_the_result(self):
        result = clean_rows([row()], CleaningConfig(max_plausible_speed_kn=42.0))
        self.assertEqual(result.config["maxPlausibleSpeedKn"], 42.0)
        self.assertTrue(result.to_dict()["config"]["treatNotAvailableSentinels"])

    def test_geo_helpers_are_consistent(self):
        from app.geo import haversine_km, implied_speed_kn, kmh_to_knots

        self.assertAlmostEqual(haversine_km(0.0, 0.0, 0.0, 0.0), 0.0)
        self.assertAlmostEqual(haversine_km(18.0, 72.0, 19.0, 72.0), 111.19, delta=0.5)
        self.assertAlmostEqual(kmh_to_knots(1.852), 1.0)
        self.assertIsNone(implied_speed_kn(10.0, 0.0),
                          "no speed can be inferred from a zero time interval")
        self.assertAlmostEqual(implied_speed_kn(1.852, 3600.0), 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
