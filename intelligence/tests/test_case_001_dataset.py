#!/usr/bin/env python3
"""ABYSS - Phase 2 validation tests for the CASE-001 synthetic demonstration dataset.

WHAT THESE TESTS PROVE
    1. exactly 12 synthetic vessels exist with the documented identities
    2. the AIS file carries the required fields and a synthetic-data label on every row
    3. timestamps, coordinates, speeds, courses and headings are valid EXCEPT the exact
       number of documented data-quality fixtures the scenario injects on purpose
    4. the scenario has the properties it claims: an observed slick downstream of the
       release point, an origin uncertainty region, a release window before observation,
       two AIS gaps (one physically feasible, one not) and the intended behaviour fixtures
    5. generation is deterministic: a fresh run reproduces the committed files byte for byte

WHAT THESE TESTS DO NOT DO
    They perform no AIS cleaning, no trajectory construction, no filtering, no behaviour
    scoring, no gap analysis and no evidence scoring. The small distance / feasibility
    helpers below exist only to check that the FIXTURE was built as documented; the
    product's equivalents belong to Phases 3-10.

RUN
    python3 -m unittest discover -s intelligence/tests -v      (from the ABYSS root)
    python3 intelligence/tests/test_case_001_dataset.py -v
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

UTC = timezone.utc

TESTS_DIR = Path(__file__).resolve().parent
INTELLIGENCE_DIR = TESTS_DIR.parent
CASE_DIR = INTELLIGENCE_DIR / "data" / "demo" / "case_001"
GENERATOR = INTELLIGENCE_DIR / "data" / "demo" / "generate_case_001.py"

#: Same fixed order as the generator's manifest (independent copy: the tests must not
#: import the generator, or a bug in it would silently validate itself).
DATASET_FILES = (
    "case_001.json",
    "demo_slick.json",
    "demo_origin_expected.json",
    "expected_ranking.json",
    "environmental/demo_environmental_field.json",
    "ais/demo_ais_positions.csv",
)

DATASET_LABEL = "Synthetic Demonstration Dataset"
AIS_FILE = "ais/demo_ais_positions.csv"

REQUIRED_COLUMNS = [
    "MMSI", "IMO", "vesselName", "vesselType", "timestamp", "latitude", "longitude",
    "SOG", "COG", "heading", "navigationStatus",
]

# --- Scenario expectations (declared here independently of the generator) ---
EXPECTED_VESSEL_IDS = [f"V{i:03d}" for i in range(1, 13)]
EXPECTED_MMSI = {f"V{i:03d}": f"9000000{i:02d}" for i in range(1, 13)}
OBSERVATION_TIME = datetime(2026, 3, 14, 6, 0, 0, tzinfo=UTC)
RELEASE_WINDOW_START = datetime(2026, 3, 13, 10, 0, 0, tzinfo=UTC)
RELEASE_WINDOW_END = datetime(2026, 3, 13, 18, 0, 0, tzinfo=UTC)
TRACK_START = datetime(2026, 3, 11, 6, 0, 0, tzinfo=UTC)
EXPECTED_DEFECT_COUNTS = {
    "duplicate_record": 4,
    "malformed_timestamp": 2,
    "invalid_coordinate": 2,
    "negative_speed": 1,
    "impossible_speed_jump": 1,
    "missing_optional_field": 3,
}
EXPECTED_MIN_RECORDS = 12 * 100  # a 72 h extract of 12 vessels cannot be this small
MIN_SLICK_TO_RELEASE_KM = 20.0

VALID_AIS_TYPE_CODES = {
    30, 31, 32, 35, 36, 37,          # fishing / towing / dredging / military / sailing / pleasure
    52, 53, 55, 60, 70, 80,          # tug, port tender, law enforcement, passenger, cargo, tanker
}


def load_json(relative: str):
    with (CASE_DIR / relative).open(encoding="utf-8") as fh:
        return json.load(fh)


def read_ais_rows():
    with (CASE_DIR / AIS_FILE).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def parse_ts(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def point_in_ring(lon, lat, ring):
    pts = list(ring)
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i][0], pts[i][1]
        x2, y2 = pts[(i + 1) % n][0], pts[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            if lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def mixture(rows):
    """Group AIS rows by MMSI, keeping only rows with parseable timestamps and valid coordinates."""
    groups = {}
    for row in rows:
        ts = parse_ts(row["timestamp"])
        if ts is None:
            continue
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except ValueError:
            continue
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180) or (lat == 0.0 and lon == 0.0):
            continue
        groups.setdefault(row["MMSI"], []).append((ts, lat, lon, float(row["SOG"])))
    for key in groups:
        groups[key].sort(key=lambda item: item[0])
    return groups


class TestGeneratorReproducibility(unittest.TestCase):
    """The dataset must be reproducible byte for byte, with no randomness involved."""

    run_a = Path()
    run_b = Path()

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="abyss_case001_")
        base = Path(cls._tmp.name)
        cls.run_a, cls.run_b = base / "run_a", base / "run_b"
        for target in (cls.run_a, cls.run_b):
            result = subprocess.run(
                [sys.executable, str(GENERATOR), "--out-dir", str(target), "--quiet"],
                capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                raise AssertionError(f"generator failed: {result.stderr}")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_two_fresh_runs_are_byte_identical(self):
        for relative in DATASET_FILES + ("manifest.json",):
            a = (self.run_a / relative).read_bytes()
            b = (self.run_b / relative).read_bytes()
            self.assertEqual(a, b, f"{relative} differs between two fresh runs")

    def test_committed_dataset_matches_a_fresh_run(self):
        for relative in DATASET_FILES + ("manifest.json",):
            committed = (CASE_DIR / relative).read_bytes()
            fresh = (self.run_a / relative).read_bytes()
            self.assertEqual(
                committed, fresh,
                f"{relative} is out of date: re-run generate_case_001.py and commit the result",
            )

    def test_manifest_hashes_match_the_committed_files(self):
        manifest = load_json("manifest.json")
        self.assertEqual([entry["path"] for entry in manifest["files"]], list(DATASET_FILES))
        for entry in manifest["files"]:
            payload = (CASE_DIR / entry["path"]).read_bytes()
            self.assertEqual(entry["bytes"], len(payload), f"size mismatch for {entry['path']}")
            self.assertEqual(
                entry["sha256"], hashlib.sha256(payload).hexdigest(),
                f"sha256 mismatch for {entry['path']}",
            )

    def test_generator_contains_no_randomness_or_wall_clock_use(self):
        source = GENERATOR.read_text(encoding="utf-8")
        forbidden = {
            "random module": r"^\s*import\s+random\b",
            "numpy random": r"np\.random",
            "uuid": r"\buuid\b",
            "wall clock (datetime.now)": r"datetime\.now\(",
            "wall clock (utcnow)": r"utcnow\(",
            "time.time": r"\btime\.time\(",
            "os.urandom": r"os\.urandom",
        }
        for label, pattern in forbidden.items():
            self.assertIsNone(
                re.search(pattern, source, flags=re.MULTILINE),
                f"generator uses {label}; the dataset must be fully deterministic",
            )

    def test_generator_is_documented_as_demo_only(self):
        source = GENERATOR.read_text(encoding="utf-8")
        self.assertIn("Synthetic Demonstration Dataset", source)
        self.assertRegex(source, r"asserts that any vessel caused an oil spill",
                         "the generator must state that it does not accuse any vessel")
        self.assertRegex(source, r"does not rank\s+or accuses any vessel|Nothing here ranks",
                         "the generator must state that nothing in it ranks or accuses a vessel")


class TestAisStructure(unittest.TestCase):
    """Identity, field and labelling requirements of the AIS extract."""

    @classmethod
    def setUpClass(cls):
        cls.rows = read_ais_rows()
        cls.case = load_json("case_001.json")

    def test_exactly_twelve_vessels_with_expected_identities(self):
        self.assertEqual(len(self.rows), len(read_ais_rows()))
        self.assertEqual(len(self.case["vessels"]), 12, "the case must register exactly 12 vessels")
        ids = [v["vesselId"] for v in self.case["vessels"]]
        self.assertEqual(ids, EXPECTED_VESSEL_IDS)
        for vessel in self.case["vessels"]:
            self.assertEqual(vessel["mmsi"], EXPECTED_MMSI[vessel["vesselId"]])
            for field in ("mmsi", "imo", "name", "typeCode", "typeLabel", "role", "roleKey"):
                self.assertTrue(str(vessel[field]).strip(), f"{vessel['vesselId']} is missing {field}")
            self.assertTrue(vessel["synthetic"], "every vessel must be flagged synthetic")
        distinct_mmsi = {row["MMSI"] for row in self.rows}
        self.assertEqual(len(distinct_mmsi), 12, "the AIS file must contain exactly 12 distinct MMSI")
        self.assertEqual(distinct_mmsi, set(EXPECTED_MMSI.values()))

    def test_required_ais_fields_are_present(self):
        with (CASE_DIR / AIS_FILE).open(newline="", encoding="utf-8") as fh:
            header = next(csv.reader(fh))
        for column in REQUIRED_COLUMNS:
            self.assertIn(column, header, f"required AIS field {column} is missing")
        self.assertEqual(header[: len(REQUIRED_COLUMNS)], REQUIRED_COLUMNS,
                         "required fields must keep the documented order")
        for row in self.rows:
            for column in REQUIRED_COLUMNS:
                self.assertIsNotNone(row.get(column), f"column {column} missing from a row")

    def test_every_row_is_labelled_as_synthetic(self):
        labels = Counter(row["datasetLabel"] for row in self.rows)
        self.assertEqual(labels, Counter({DATASET_LABEL: len(self.rows)}),
                         "every AIS row must carry the synthetic-data label")

    def test_record_volume_is_sane_and_matches_the_manifest(self):
        self.assertGreater(len(self.rows), EXPECTED_MIN_RECORDS)
        manifest = load_json("manifest.json")
        self.assertEqual(manifest["counts"]["aisRecords"], len(self.rows))
        self.assertEqual(manifest["counts"]["vessels"], 12)
        self.assertEqual(self.case["aisExtract"]["recordCount"], len(self.rows))

    def test_rows_with_parseable_timestamps_are_in_chronological_order(self):
        parsed = [parse_ts(row["timestamp"]) for row in self.rows]
        ordered = [ts for ts in parsed if ts is not None]
        self.assertEqual(ordered, sorted(ordered), "the extract should be time-ordered")
        self.assertEqual(sum(1 for ts in parsed if ts is None), 2,
                         "exactly two rows carry the documented malformed timestamps")

    def test_mmsi_and_imo_values_are_format_valid_placeholders(self):
        imo_pattern = re.compile(r"^9990\d{2}\d$")
        for row in self.rows:
            self.assertRegex(row["MMSI"], r"^9000000\d{2}$", "MMSI should use the synthetic block")
            imo = row["IMO"]
            self.assertRegex(imo, imo_pattern.pattern, "IMO should use the synthetic block")
            # Real IMO check-digit rule, used here to keep the field realistic.
            weights = (7, 6, 5, 4, 3, 2)
            total = sum(int(d) * w for d, w in zip(imo[:6], weights))
            self.assertEqual(int(imo[6]), total % 10, f"IMO {imo} fails its check digit")

    def test_ship_type_codes_are_plausible_ais_codes(self):
        for row in self.rows:
            self.assertIn(int(row["vesselType"]), VALID_AIS_TYPE_CODES,
                          f"unexpected vessel type code {row['vesselType']}")


class TestAisDataQuality(unittest.TestCase):
    """The documented data-quality fixtures must exist, and nothing else may be broken."""

    @classmethod
    def setUpClass(cls):
        cls.rows = read_ais_rows()
        cls.case = load_json("case_001.json")
        cls.by_mmsi = {v["mmsi"]: v["vesselId"] for v in cls.case["vessels"]}

    def test_timestamps_are_valid_except_the_two_documented_fixtures(self):
        bad = [row for row in self.rows if parse_ts(row["timestamp"]) is None]
        self.assertEqual(len(bad), EXPECTED_DEFECT_COUNTS["malformed_timestamp"])
        self.assertEqual({row["MMSI"] for row in bad}, {EXPECTED_MMSI["V008"]})
        self.assertEqual({row["timestamp"] for row in bad},
                         {"2026-03-12T25:61:00Z", "12/03/2026 08:00"})
        for row in self.rows:
            if parse_ts(row["timestamp"]) is not None:
                continue
            self.assertTrue(row["timestamp"], "a malformed timestamp must still be present")

    def test_coordinates_are_valid_except_the_two_documented_fixtures(self):
        invalid = []
        for row in self.rows:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180) or (lat == 0.0 and lon == 0.0):
                invalid.append(row)
        self.assertEqual(len(invalid), EXPECTED_DEFECT_COUNTS["invalid_coordinate"])
        self.assertEqual({self.by_mmsi[row["MMSI"]] for row in invalid}, {"V010", "V012"})
        self.assertTrue(any(float(row["latitude"]) == 0.0 and float(row["longitude"]) == 0.0
                            for row in invalid), "the null-island fixture must exist")
        self.assertTrue(any(float(row["latitude"]) == 95.2 for row in invalid),
                        "the out-of-range latitude fixture must exist")

    def test_speeds_are_plausible_except_the_one_documented_fixture(self):
        negative = [row for row in self.rows if float(row["SOG"]) < 0]
        self.assertEqual(len(negative), EXPECTED_DEFECT_COUNTS["negative_speed"])
        self.assertEqual(negative[0]["SOG"], "-3.0")
        self.assertEqual(self.by_mmsi[negative[0]["MMSI"]], "V006")
        for row in self.rows:
            sog = float(row["SOG"])
            self.assertTrue(sog < 30.0 or row in negative,
                            f"implausible SOG {sog} outside the documented fixture")

    def test_courses_and_headings_are_in_range(self):
        for row in self.rows:
            cog = float(row["COG"])
            self.assertTrue(0.0 <= cog < 360.0, f"COG out of range: {cog}")
            if row["heading"]:
                heading = int(row["heading"])
                self.assertTrue(0 <= heading <= 359, f"heading out of range: {heading}")
            if row["navigationStatus"]:
                self.assertTrue(0 <= int(row["navigationStatus"]) <= 15,
                                "navigation status must be a plausible AIS value")

    def test_duplicate_records_are_exactly_the_documented_fixtures(self):
        pairs = Counter((row["MMSI"], row["timestamp"]) for row in self.rows)
        duplicated = {key for key, count in pairs.items() if count > 1}
        self.assertEqual(len(duplicated), EXPECTED_DEFECT_COUNTS["duplicate_record"])
        self.assertEqual({self.by_mmsi[key[0]] for key in duplicated}, {"V007"})
        for mmsi, timestamp in duplicated:
            same = [row for row in self.rows if row["MMSI"] == mmsi and row["timestamp"] == timestamp]
            self.assertEqual(len(same), 2, "a duplicate fixture must appear exactly twice")
            self.assertEqual(same[0]["latitude"], same[1]["latitude"])
            self.assertEqual(same[0]["longitude"], same[1]["longitude"])
            self.assertEqual(same[0]["SOG"], same[1]["SOG"])
            self.assertEqual(same[0]["COG"], same[1]["COG"])

    def test_one_impossible_speed_jump_is_injected_and_no_other_exists(self):
        offenders = []
        worst = 0.0
        for mmsi, group in mixture(self.rows).items():
            for first, second in zip(group, group[1:]):
                hours = (second[0] - first[0]).total_seconds() / 3600.0
                if hours <= 0:
                    continue
                knots = haversine_km(first[1], first[2], second[1], second[2]) / hours / 1.852
                worst = max(worst, knots)
                if knots > 60.0:
                    offenders.append((self.by_mmsi[mmsi], knots, first[0], second[0]))
        # The injected record teleports out and back, so one bad row produces exactly two
        # impossible consecutive steps. This is stated in the case configuration.
        self.assertEqual(len(offenders), 2,
                         f"one injected bad row should yield exactly two impossible steps: {offenders}")
        self.assertEqual({item[0] for item in offenders}, {"V006"},
                         "only the documented vessel may contain an impossible step")
        for _vessel, knots, first_ts, second_ts in offenders:
            self.assertGreater(knots, 300.0, "the injected jump must be far beyond any vessel speed")
            self.assertEqual((second_ts - first_ts).total_seconds(), 300.0)
        shared_rows = {offenders[0][3]} & {offenders[1][2]}
        self.assertEqual(len(shared_rows), EXPECTED_DEFECT_COUNTS["impossible_speed_jump"],
                         "both impossible steps must be produced by the same single injected row")
        self.assertGreater(worst, 300.0)

    def test_missing_optional_fields_are_the_documented_rows(self):
        blank = [row for row in self.rows if not row["heading"] and not row["navigationStatus"]]
        self.assertEqual(len(blank), EXPECTED_DEFECT_COUNTS["missing_optional_field"])
        self.assertEqual({self.by_mmsi[row["MMSI"]] for row in blank}, {"V011"})
        for row in blank:
            self.assertTrue(row["timestamp"] and row["latitude"] and row["longitude"],
                            "a row with missing optional fields must still be otherwise valid")

    def test_defect_inventory_matches_the_case_configuration(self):
        counts = Counter(d["category"] for d in self.case["injectedDefects"])
        self.assertEqual(dict(counts), EXPECTED_DEFECT_COUNTS)
        self.assertEqual(self.case["counts"]["defectRows"], sum(EXPECTED_DEFECT_COUNTS.values()))
        for defect in self.case["injectedDefects"]:
            self.assertTrue(defect["defectId"].startswith("D"))
            self.assertTrue(defect["description"])
            self.assertIn("expectedPhase3Action", defect,
                          "each injected defect must state what Phase 3 cleaning should do")


class TestScenarioDesign(unittest.TestCase):
    """The scenario must actually have the forensic properties it claims to have."""

    @classmethod
    def setUpClass(cls):
        cls.rows = read_ais_rows()
        cls.case = load_json("case_001.json")
        cls.slick = load_json("demo_slick.json")
        cls.fixture = load_json("demo_origin_expected.json")
        cls.ranking = load_json("expected_ranking.json")
        cls.groups = mixture(cls.rows)
        cls.by_mmsi = {v["mmsi"]: v["vesselId"] for v in cls.case["vessels"]}
        cls.origin = (cls.fixture["trueReleasePoint"]["lat"], cls.fixture["trueReleasePoint"]["lon"])
        cls.origin_ring = cls.fixture["expectedOriginRegion"]["coordinates"][0]
        cls.slick_centroid = (cls.slick["centroid"]["lat"], cls.slick["centroid"]["lon"])

    # --- helpers ---------------------------------------------------------
    def rows_for(self, vessel_id):
        mmsi = EXPECTED_MMSI[vessel_id]
        return [row for row in self.rows if row["MMSI"] == mmsi]

    def min_distance_during_window(self, vessel_id):
        distances = [
            haversine_km(self.origin[0], self.origin[1], lat, lon)
            for ts, lat, lon, _sog in self.groups[EXPECTED_MMSI[vessel_id]]
            if RELEASE_WINDOW_START <= ts <= RELEASE_WINDOW_END
        ]
        return min(distances) if distances else None

    def records_inside_origin_region(self, vessel_id):
        return [
            (ts, lat, lon)
            for ts, lat, lon, _sog in self.groups[EXPECTED_MMSI[vessel_id]]
            if point_in_ring(lon, lat, self.origin_ring)
        ]

    def bridge_speed_kn(self, vessel_id, start, end):
        group = self.groups[EXPECTED_MMSI[vessel_id]]
        before = [item for item in group if item[0] < start]
        after = [item for item in group if item[0] > end]
        self.assertTrue(before, f"{vessel_id} has no records before the gap")
        self.assertTrue(after, f"{vessel_id} has no records after the gap")
        last_before, first_after = before[-1], after[0]
        hours = (first_after[0] - last_before[0]).total_seconds() / 3600.0
        distance = haversine_km(last_before[1], last_before[2], first_after[1], first_after[2])
        return distance / hours / 1.852

    # --- geometry --------------------------------------------------------
    def test_observed_slick_is_downstream_of_the_release_point(self):
        separation = haversine_km(self.origin[0], self.origin[1], *self.slick_centroid)
        self.assertGreaterEqual(separation, MIN_SLICK_TO_RELEASE_KM,
                                "the demo must show that observed position != release position")
        self.assertAlmostEqual(separation, self.fixture["observedVsRelease"]["separationKm"], delta=0.5)
        self.assertNotAlmostEqual(separation, 0.0, places=3)

    def test_origin_region_contains_the_release_point_and_excludes_the_slick(self):
        self.assertTrue(point_in_ring(self.origin[1], self.origin[0], self.origin_ring))
        self.assertFalse(point_in_ring(self.slick_centroid[1], self.slick_centroid[0], self.origin_ring))
        self.assertGreater(self.fixture["expectedOriginRegion"]["uncertaintyRadiusKm"], 0.0)
        self.assertGreater(self.fixture["expectedOriginRegion"]["areaKm2"], 0.0)

    def test_release_window_precedes_the_observation(self):
        self.assertLess(RELEASE_WINDOW_START, RELEASE_WINDOW_END)
        self.assertLessEqual(RELEASE_WINDOW_END, OBSERVATION_TIME)
        self.assertEqual(self.case["observation"]["observedAt"], "2026-03-14T06:00:00Z")
        self.assertEqual(self.case["origin"]["releaseWindow"]["start"], "2026-03-13T10:00:00Z")

    def test_slick_geometry_is_usable(self):
        ring = self.slick["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1], "a GeoJSON polygon ring must be closed")
        self.assertGreaterEqual(self.slick["areaKm2"], 20.0)
        self.assertFalse(self.slick["lookAlikeWarning"])
        self.assertTrue(0.0 < self.slick["detectionConfidence"] < 1.0)

    def test_no_answer_key_is_published_in_the_case_configuration(self):
        serialised = json.dumps(self.case)
        self.assertNotIn("trueReleasePoint", serialised)
        self.assertIn("reservedOriginFixtureFile", self.case)
        self.assertIn("must never be surfaced", self.case["reservedOriginFixtureNote"])
        self.assertIn("never be shown", self.fixture["warning"])

    # --- vessel roles ----------------------------------------------------
    def test_v001_is_inside_the_origin_region_during_the_release_window(self):
        inside = [(ts, lat, lon) for ts, lat, lon in self.records_inside_origin_region("V001")
                  if RELEASE_WINDOW_START <= ts <= RELEASE_WINDOW_END]
        self.assertTrue(inside, "V001 must be inside the origin region during the window")
        sog = [float(row["SOG"]) for row in self.rows_for("V001") if float(row["SOG"]) > 0]
        self.assertLessEqual(min(sog), 3.0, "V001 must show its documented slowdown")
        self.assertGreaterEqual(max(sog), 10.0, "V001 must also show its normal transit speed")

    def test_v002_gap_overlaps_the_window_and_is_physically_feasible(self):
        gap = next(g for g in self.fixture["expectedGapFixtures"] if g["vesselId"] == "V002")
        self.assertEqual(gap["start"], "2026-03-13T12:00:00Z")
        self.assertEqual(gap["end"], "2026-03-13T16:00:00Z")
        self.assertLessEqual(RELEASE_WINDOW_START, parse_ts(gap["start"]))
        self.assertLessEqual(parse_ts(gap["end"]), RELEASE_WINDOW_END)
        implied = self.bridge_speed_kn("V002", parse_ts(gap["start"]), parse_ts(gap["end"]))
        self.assertLessEqual(implied, 15.0, f"V002's gap should be feasible, implied {implied:.1f} kn")
        self.assertGreaterEqual(implied, 2.0, "a gap bridge must not be suspiciously slow either")

    def test_v003_gap_is_physically_impossible(self):
        gap = next(g for g in self.fixture["expectedGapFixtures"] if g["vesselId"] == "V003")
        self.assertEqual(gap["durationHours"], 4.0)
        implied = self.bridge_speed_kn("V003", parse_ts(gap["start"]), parse_ts(gap["end"]))
        self.assertGreaterEqual(implied, 30.0, f"V003's gap must be impossible, implied {implied:.1f} kn")
        self.assertGreater(implied, 3.0 * self.bridge_speed_kn("V002", parse_ts(gap["start"]), parse_ts(gap["end"])))

    def test_v004_is_nearest_to_the_slick_but_far_from_the_origin(self):
        at_observation = {}
        for vessel_id in EXPECTED_VESSEL_IDS:
            group = self.groups[EXPECTED_MMSI[vessel_id]]
            last = max((item for item in group if item[0] <= OBSERVATION_TIME), key=lambda item: item[0])
            at_observation[vessel_id] = haversine_km(*self.slick_centroid, last[1], last[2])
        nearest = min(at_observation, key=at_observation.get)
        self.assertEqual(nearest, "V004", f"V004 should be closest to the slick, got {nearest}")
        self.assertLess(at_observation["V004"], 20.0)
        self.assertGreater(self.min_distance_during_window("V004"), 100.0,
                           "V004 must be far from the ORIGIN during the release window")

    def test_v005_reaches_the_origin_only_after_the_window(self):
        self.assertGreater(self.min_distance_during_window("V005"), 100.0)
        group = self.groups[EXPECTED_MMSI["V005"]]
        closest = min(group, key=lambda item: haversine_km(self.origin[0], self.origin[1], item[1], item[2]))
        self.assertGreater(closest[0], RELEASE_WINDOW_END,
                           "V005's closest approach must come after the window closes")
        self.assertLess(haversine_km(self.origin[0], self.origin[1], closest[1], closest[2]), 10.0)

    def test_v006_anomaly_without_location(self):
        sog = [float(row["SOG"]) for row in self.rows_for("V006") if float(row["SOG"]) > 0]
        self.assertGreater(max(sog) - min(sog), 4.0, "V006 must show strong speed variability")
        self.assertGreater(self.min_distance_during_window("V006"), 150.0,
                           "V006's anomaly must sit far from the origin region")

    def test_control_and_distractor_vessels_are_not_spatially_compatible(self):
        for vessel_id in ("V007", "V008", "V009", "V010", "V011", "V012"):
            distance = self.min_distance_during_window(vessel_id)
            self.assertIsNotNone(distance, f"{vessel_id} should have records inside the window")
            self.assertGreater(distance, 50.0,
                               f"{vessel_id} must not be spatially compatible ({distance:.1f} km)")

    def test_legitimate_stationary_behaviour_is_present_far_from_the_origin(self):
        for vessel_id, minimum in (("V008", 20), ("V011", 20)):
            rows = self.rows_for(vessel_id)
            stationary = [row for row in rows if float(row["SOG"]) < 1.0]
            self.assertGreaterEqual(len(stationary), minimum,
                                    f"{vessel_id} should contain documented stationary periods")

    def test_expected_ranking_declares_roles_and_test_case_mapping(self):
        self.assertEqual(sorted(self.ranking["topCandidates"]), ["V001", "V002"])
        self.assertIn("V004", self.ranking["mustNotRankFirst"])
        mapping = self.ranking["testCaseMapping"]
        for key in ("A_correct_location_and_time", "B_correct_location_wrong_time",
                    "D_gap_with_impossible_travel", "E_gap_physically_compatible",
                    "F_anomaly_without_location", "G_nearest_vessel_not_highest_scoring"):
            self.assertIn(key, mapping)
        self.assertIn("V002", self.ranking["mustRankBelow"]["V003"])
        self.assertIn("V001", self.ranking["mustRankBelow"]["V004"])

    def test_every_vessel_has_a_documented_summary(self):
        summarised = {s["vesselId"] for s in self.fixture["vesselSummaries"]}
        self.assertEqual(summarised, set(EXPECTED_VESSEL_IDS))
        for summary in self.fixture["vesselSummaries"]:
            self.assertIn("roleKey", summary)
            self.assertGreater(summary["recordCount"], 0)
            self.assertIsNotNone(summary["expected"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
