#!/usr/bin/env python3
"""ABYSS - Phase 10 tests for explainable evidence scoring and candidate ranking.

WHAT THESE TESTS PROVE
    1. every candidate carries all five named factors with one plain-language reason
       each, INCLUDING the factors that scored zero, and the reported total equals the
       sum of the reported factor points. A zero without a reason would be
       indistinguishable from a bug. The default weights are exactly the table in
       docs/methodology.md section 7 (spatial 35 - temporal 25 - trajectory 20 -
       behaviour 10 - gap 10), which makes a gap the lightest factor of the five
    2. the golden rules hold across all twelve vessels:
       * a gap can never contribute more than the configured cap (30 % of the gap weight)
         - V002 is given the maximum permitted 3.0 of 10, V003 gets nothing because its
         identical gap is physically impossible (cases D and E);
       * the ABSENCE of a gap is never rewarded - V007's clean track explains "the
         absence of a gap is not evidence either" and scores zero for it;
       * a behavioural anomaly outside the origin region is reported as context and
         scores zero - V006's 0.35 anomaly reads "context only, not evidence" (case F);
       * the vessel nearest to the observed slick is neither first nor credited for
         proximity - V004's counterfactual is the one printed at rank 1 (case G)
    3. the eight ordering properties DECLARED IN expected_ranking.json are satisfied by
       the assembled engine. That fixture states they are "intended properties of the
       synthetic scenario, to be satisfied by the Phase 10 scoring engine", so each one
       is asserted here individually, including the rank-band promises (V004 mid, V006
       outside the top five, V012 bottom)
    4. ranking mechanics are honest and deterministic: descending totals, ties surfaced
       as tie groups rather than hidden, a counterfactual on every entry, an
       identifier tie-break that is labelled "not evidential", and duplicate MMSIs
       rejected because they would make the order unstable
    5. the weights are genuinely configurable: re-running with the gap weight set to 100
       and everything else to zero promotes the gap-compatible vessel V002 to rank 1,
       which proves the ranking follows the configured evidence rather than a hard-coded
       answer

WHAT THESE TESTS DO NOT DO
    No detection, no hindcast tuning, no AIS ingestion. This module tests the engine and
    the ordering; the pipeline around them is covered by test_investigation_pipeline.py.

RUN (needs the project virtual environment)
    .venv/bin/python -m unittest discover -s intelligence/tests -v
    .venv/bin/python intelligence/tests/test_scoring_engine.py -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

INTELLIGENCE_DIR = Path(__file__).resolve().parent.parent
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from app.investigation import run_investigation
from app.scoring.engine import (FACTOR_KEYS, CandidateEvidence, EvidenceWeights,
                                ScoredCandidate, ScoringConfig, score_candidate)
from app.scoring.ranking import rank_candidates

V001, V002, V003 = "900000001", "900000002", "900000003"
V004, V005, V006 = "900000004", "900000005", "900000006"
V007, V008, V009 = "900000007", "900000008", "900000009"
V010, V011, V012 = "900000010", "900000011", "900000012"

MMSI_TO_VESSEL = {900000001 + index: f"V{index + 1:03d}" for index in range(12)}
DEFAULT_WEIGHTS = {"spatial": 35.0, "gap": 10.0, "trajectory": 20.0,
                   "behaviour": 10.0, "temporal": 25.0}
TOP_CANDIDATE_MMSI = "900000001"
TIE_GROUP_SIZE = 9                     # the nine vessels with no evidence of any kind
GAP_CAP_SHARE = 0.30                   # docs/methodology.md section 5
MAX_GAP_POINTS = DEFAULT_WEIGHTS["gap"] * GAP_CAP_SHARE        # 3.0 of 100
SPATIAL_FALLOFF_KM = 30.0
MAX_TOTAL = 100.0

_PIPELINE = None


def pipeline():
    """One assembled run shared by every class (the pipeline is deterministic)."""
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = run_investigation().to_dict()
    return _PIPELINE


def entries_by_vessel() -> dict:
    return {entry["vesselId"]: entry for entry in pipeline()["ranking"]["entries"]}


def expected_ranking_fixture() -> dict:
    path = (INTELLIGENCE_DIR / "data" / "demo" / "case_001" / "expected_ranking.json")
    return json.loads(path.read_text(encoding="utf-8"))


class TestEvidenceWeights(unittest.TestCase):
    """Weights are configuration: validated, reported, and genuinely variable."""

    def test_default_weights_sum_to_one_hundred(self):
        weights = EvidenceWeights()
        self.assertEqual(weights.total, MAX_TOTAL)
        self.assertEqual(weights.describe(), DEFAULT_WEIGHTS)

    def test_negative_weight_is_rejected(self):
        for key in FACTOR_KEYS:
            with self.assertRaises(ValueError, msg=f"negative {key} must be rejected"):
                EvidenceWeights(**{key: -1.0})

    def test_all_zero_weights_are_rejected(self):
        with self.assertRaises(ValueError):
            EvidenceWeights(spatial=0.0, gap=0.0, trajectory=0.0, behaviour=0.0,
                            temporal=0.0)

    def test_unknown_factor_lookup_fails_loudly(self):
        with self.assertRaises(KeyError):
            EvidenceWeights().get("vibes")

    def test_weights_may_sum_to_anything_positive_and_still_report_correctly(self):
        weights = EvidenceWeights(spatial=10.0, gap=10.0, trajectory=10.0,
                                  behaviour=10.0, temporal=10.0)
        self.assertEqual(weights.total, 50.0)
        self.assertEqual(sorted(weights.describe()), sorted(FACTOR_KEYS))

    def test_configurable_weights_change_the_outcome_not_just_the_numbers(self):
        """With gap evidence alone worth 100 points, V002 must lead the ranking."""
        gap_only = EvidenceWeights(spatial=0.0, gap=100.0, trajectory=0.0,
                                   behaviour=0.0, temporal=0.0)
        payload = run_investigation(weights=gap_only).to_dict()
        ranked = payload["ranking"]["entries"]
        self.assertEqual(ranked[0]["vesselId"], "V002")
        self.assertEqual(ranked[0]["totalScore"], 30.0)
        self.assertEqual({entry["vesselId"] for entry in ranked
                          if entry["totalScore"] > 0.0}, {"V002"})


class TestFactorTransparency(unittest.TestCase):
    """Every factor is reported, bounded, explained, and arithmetically consistent."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = pipeline()
        cls.entries = cls.payload["ranking"]["entries"]

    def test_every_candidate_reports_all_five_factors_and_five_reasons(self):
        for entry in self.entries:
            self.assertEqual(list(entry["factors"]), list(FACTOR_KEYS), entry["vesselId"])
            self.assertEqual(len(entry["reasons"]), len(FACTOR_KEYS), entry["vesselId"])

    def test_reported_total_equals_the_sum_of_the_reported_factor_points(self):
        for entry in self.entries:
            total = sum(entry["factors"][key]["points"] for key in FACTOR_KEYS)
            self.assertAlmostEqual(entry["totalScore"], round(total, 3), places=3,
                                   msg=entry["vesselId"])

    def test_no_candidate_exceeds_the_configured_maximum(self):
        for entry in self.entries:
            self.assertLessEqual(entry["totalScore"], MAX_TOTAL, entry["vesselId"])
            for key in FACTOR_KEYS:
                factor = entry["factors"][key]
                self.assertEqual(factor["maxPoints"], DEFAULT_WEIGHTS[key])
                self.assertLessEqual(factor["points"], factor["maxPoints"] + 1e-9)
                self.assertGreaterEqual(factor["points"], 0.0)

    def test_every_reason_names_its_factor_and_shows_its_points(self):
        for entry in self.entries:
            for reason in entry["reasons"]:
                self.assertRegex(reason, r"\[\d+(\.\d+)?/\d+(\.\d+)?\]$")
            text = " | ".join(entry["reasons"])
            for key in ("distance to origin region", "AIS-gap behaviour",
                        "course-change correlation", "stop/slow pattern",
                        "proximity to release window"):
                self.assertIn(key, text, entry["vesselId"])

    def test_a_zero_factor_always_explains_why_it_is_zero(self):
        """A silent zero is indistinguishable from an unreported bug."""
        reasons = {entry["vesselId"]: entry["reasons"] for entry in self.entries}
        self.assertIn("no AIS gap - the absence of a gap is not evidence either",
                      " ".join(reasons["V007"]))
        self.assertIn("no transit of the origin region during the window",
                      " ".join(reasons["V004"]))
        self.assertIn("never observed inside the origin region during the window",
                      " ".join(reasons["V004"]))



class TestGoldenRules(unittest.TestCase):
    """The constraints that keep this tool from overclaiming."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.entries = entries_by_vessel()

    def points(self, vessel: str, factor: str) -> float:
        return self.entries[vessel]["factors"][factor]["points"]

    def reasons(self, vessel: str) -> str:
        return " ".join(self.entries[vessel]["reasons"])

    # --- rule 1: a gap is never strong evidence ------------------------------
    def test_no_vessel_ever_receives_more_than_the_gap_cap(self):
        limit = DEFAULT_WEIGHTS["gap"] * GAP_CAP_SHARE
        for vessel, entry in self.entries.items():
            self.assertLessEqual(entry["factors"]["gap"]["points"], limit + 1e-9, vessel)

    def test_the_feasible_gap_takes_exactly_the_cap_and_the_impossible_one_nothing(self):
        """The V002/V003 pair, now at the score level (cases E and D)."""
        self.assertAlmostEqual(self.points("V002", "gap"), MAX_GAP_POINTS, places=3)
        self.assertEqual(self.points("V003", "gap"), 0.0)
        self.assertIn("weak, capped evidence", self.reasons("V002"))
        self.assertIn("physically impossible to traverse", self.reasons("V003"))

    def test_absence_of_a_gap_is_not_evidence_either(self):
        self.assertEqual(self.points("V007", "gap"), 0.0)
        self.assertIn("the absence of a gap is not evidence either",
                      self.reasons("V007"))

    def test_the_pair_with_identical_gap_timing_is_separated_by_physics_only(self):
        """V002 and V003 differ on the gap factor and almost nothing else: the 3-point
        gap difference dominates a 0.075-point behavioural difference by 40x."""
        deltas = {factor: round(self.points("V002", factor) - self.points("V003", factor), 6)
                  for factor in FACTOR_KEYS}
        non_zero = {factor: value for factor, value in deltas.items() if value}
        self.assertEqual(set(non_zero), {"gap", "behaviour"})
        self.assertGreater(non_zero["gap"], 10 * abs(non_zero["behaviour"]))
        self.assertGreater(self.entries["V002"]["totalScore"],
                           self.entries["V003"]["totalScore"])

    # --- rule 2: behaviour outside the region is context, not evidence --------
    def test_a_behaviour_anomaly_outside_the_region_scores_zero(self):
        entry = self.entries["V006"]
        self.assertEqual(entry["factors"]["behaviour"]["points"], 0.0)
        self.assertGreater(entry["factors"]["behaviour"]["detail"]["rawAnomaly"], 0.30)
        self.assertFalse(entry["factors"]["behaviour"]["detail"]["scoredEligible"])
        self.assertIn("context only, not evidence", self.reasons("V006"))

    def test_a_behaviour_anomaly_inside_the_region_does_score(self):
        detail = self.entries["V001"]["factors"]["behaviour"]["detail"]
        self.assertTrue(detail["scoredEligible"])
        self.assertGreater(detail["rawAnomaly"], 0.30)
        self.assertGreater(self.points("V001", "behaviour"), 0.0)

    # --- rule 3: proximity to the slick is not proximity to the release -------
    def test_the_slick_nearest_vessel_earns_nothing_from_proximity(self):
        entry = self.entries["V004"]
        self.assertEqual(entry["totalScore"], 0.0)
        self.assertEqual(entry["factors"]["spatial"]["points"], 0.0)
        self.assertIn("beyond the 30 km falloff, no spatial evidence",
                      self.reasons("V004"))
        self.assertLess(entry["distanceToSlickKm"], 20.0)

    def test_right_place_wrong_time_is_stated_as_such(self):
        """Case B: V005 crosses the region after the window closed."""
        self.assertEqual(self.points("V005", "temporal"), 0.0)
        self.assertIn("AFTER the window closed", self.reasons("V005"))
        self.assertIn("right place, wrong time", self.reasons("V005"))
        self.assertEqual(self.entries["V005"]["totalScore"], 0.0)

    def test_inside_the_region_during_the_window_maximises_spatial_and_temporal(self):
        for vessel in ("V001", "V002", "V003"):
            self.assertEqual(self.points(vessel, "spatial"), DEFAULT_WEIGHTS["spatial"])
            self.assertEqual(self.points(vessel, "temporal"), DEFAULT_WEIGHTS["temporal"])
            self.assertEqual(self.points(vessel, "trajectory"),
                             DEFAULT_WEIGHTS["trajectory"])



class TestDeclaredScenarioProperties(unittest.TestCase):
    """The eight properties expected_ranking.json declares, asserted one by one."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = expected_ranking_fixture()
        cls.entries = entries_by_vessel()
        cls.rank_of = {vessel: entry["rank"] for vessel, entry in cls.entries.items()}
        cls.score_of = {vessel: entry["totalScore"] for vessel, entry in cls.entries.items()}

    def test_the_fixture_is_a_fixture_and_says_so(self):
        self.assertTrue(self.fixture["synthetic"])
        self.assertIn("to be satisfied by the Phase 10 scoring engine",
                      self.fixture["status"])
        self.assertEqual(len(self.fixture["expectedOrderingProperties"]), 8)

    def test_property_1_v001_and_v002_form_the_top_two_candidates(self):
        top_two = {vessel for vessel, rank in self.rank_of.items() if rank <= 2}
        self.assertEqual(top_two, set(self.fixture["topCandidates"]))

    def test_property_2_v003_ranks_strictly_below_v002(self):
        self.assertGreater(self.rank_of["V003"], self.rank_of["V002"])

    def test_property_3_v004_is_not_ranked_first(self):
        for vessel in self.fixture["mustNotRankFirst"]:
            self.assertNotEqual(self.rank_of[vessel], 1)

    def test_property_4_v005_ranks_below_v001_and_v002(self):
        for higher in ("V001", "V002"):
            self.assertGreater(self.rank_of["V005"], self.rank_of[higher])

    def test_property_5_v006_is_not_in_the_top_five(self):
        self.assertGreater(self.rank_of["V006"], 5)

    def test_property_6_every_distractor_ranks_below_a_compatible_candidate(self):
        for vessel in self.fixture["mustRankBelow"]:
            self.assertGreater(self.rank_of[vessel],
                               min(self.rank_of["V001"], self.rank_of["V002"]),
                               f"{vessel} must not outrank both top candidates")

    def test_property_7_v007_is_not_promoted_by_its_missing_gap(self):
        self.assertEqual(self.entries["V007"]["factors"]["gap"]["points"], 0.0)
        self.assertGreater(self.rank_of["V007"], 2)

    def test_property_8_v004_outranks_v006_in_slick_proximity_terms(self):
        """Both sit outside the evidence, but the vessel nearer the slick is listed first
        and the rank-1 counterfactual explains why that proximity bought nothing."""
        self.assertLess(self.entries["V004"]["distanceToSlickKm"],
                        self.entries["V006"]["distanceToSlickKm"])
        self.assertLessEqual(self.rank_of["V004"], self.rank_of["V006"])

    def test_the_declared_must_rank_below_matrix_holds(self):
        for vessel, betters in self.fixture["mustRankBelow"].items():
            for better in betters:
                self.assertGreater(self.rank_of[vessel], self.rank_of[better],
                                   f"{vessel} must rank below {better}")

    def test_the_declared_rank_bands_are_ordered_as_promised(self):
        self.assertEqual({v for v, r in self.rank_of.items() if r <= 2},
                         {"V001", "V002"})
        self.assertLessEqual(self.rank_of["V003"], 3)
        self.assertGreater(self.rank_of["V004"], 1)
        self.assertLess(self.rank_of["V006"], self.rank_of["V012"])
        self.assertGreater(self.rank_of["V012"], self.rank_of["V001"])
        self.assertEqual(self.rank_of["V012"], 12, "V012 is the designed bottom entry")

    def test_the_test_case_mapping_matches_the_measured_behaviour(self):
        mapping = self.fixture["testCaseMapping"]
        self.assertEqual(mapping["A_correct_location_and_time"], "V001")
        self.assertEqual(mapping["B_correct_location_wrong_time"], "V005")
        self.assertEqual(mapping["E_gap_physically_compatible"], "V002")
        self.assertEqual(mapping["D_gap_with_impossible_travel"], "V003")
        self.assertIn("V006", mapping["F_anomaly_without_location"])
        self.assertGreater(self.rank_of["V005"], 2)          # case B
        self.assertNotEqual(self.rank_of["V004"], 1)          # case C/G
        self.assertEqual(self.entries["V003"]["factors"]["gap"]["points"], 0.0)  # case D
        self.assertAlmostEqual(self.entries["V002"]["factors"]["gap"]["points"], 3.0)  # E
        self.assertEqual(self.entries["V006"]["factors"]["behaviour"]["points"], 0.0)  # F



class TestRankingMechanics(unittest.TestCase):
    """Ordering must be deterministic, explicit about ties, and never re-score."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = pipeline()
        cls.ranking = cls.payload["ranking"]
        cls.entries = cls.ranking["entries"]

    def test_ranks_are_contiguous_and_ordered_by_descending_score(self):
        self.assertEqual([entry["rank"] for entry in self.entries],
                         list(range(1, len(self.entries) + 1)))
        scores = [entry["totalScore"] for entry in self.entries]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_ties_are_surfaced_as_a_group_rather_than_hidden(self):
        groups = self.ranking["tieGroups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), TIE_GROUP_SIZE)
        self.assertEqual({MMSI_TO_VESSEL[int(mmsi)] for mmsi in groups[0]},
                         {"V004", "V005", "V006", "V007", "V008", "V009", "V010",
                          "V011", "V012"})
        self.assertTrue(self.ranking["notes"][1].startswith("an equal score is a real"))

    def test_the_ordering_rule_is_stated_and_labels_the_tie_break(self):
        self.assertIn("descending total score", self.ranking["orderingRule"])
        self.assertIn("ascending MMSI", self.ranking["orderingRule"])
        tied = [entry["counterfactual"]["text"] for entry in self.entries
                if "MMSI tie-break" in entry["counterfactual"]["text"]]
        self.assertEqual(len(tied), TIE_GROUP_SIZE - 1)
        self.assertIn("not evidential", tied[0])

    def test_every_entry_carries_a_counterfactual_with_factor_margins(self):
        for entry in self.entries:
            counterfactual = entry["counterfactual"]
            self.assertIsNotNone(counterfactual, entry["vesselId"])
            self.assertTrue(counterfactual["text"], entry["vesselId"])
            self.assertIsInstance(counterfactual["factorDeltas"], dict)

    def test_rank_one_explains_why_the_slick_nearest_vessel_is_not_first(self):
        """Case G, told at the top of the ranking rather than in a footnote."""
        top = self.entries[0]
        nearest = min(self.entries, key=lambda entry: entry["distanceToSlickKm"])
        self.assertEqual(top["vesselId"], "V001")
        self.assertEqual(nearest["vesselId"], "V004")
        counterfactual = top["counterfactual"]
        self.assertEqual(counterfactual["againstMmsi"], nearest["mmsi"])
        self.assertIn("nearest to the observed slick", counterfactual["text"])
        self.assertIn("slick proximity is not release proximity", counterfactual["text"])
        self.assertEqual(counterfactual["factorDeltas"]["spatial"],
                         DEFAULT_WEIGHTS["spatial"])

    def test_ranking_is_a_deterministic_reordering_of_scored_candidates(self):
        scored = [ScoredCandidate(mmsi=entry["mmsi"], vessel_id=entry["vesselId"],
                                  name=entry["name"], vessel_type=entry["vesselType"],
                                  total=entry["totalScore"], factors=entry["factors"],
                                  reasons=entry["reasons"],
                                  distance_to_slick_km=entry["distanceToSlickKm"])
                  for entry in reversed(self.entries)]
        first = rank_candidates(scored).to_dict()
        second = rank_candidates(scored).to_dict()
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))
        self.assertEqual([entry["vesselId"] for entry in first["entries"]],
                         [entry["vesselId"] for entry in self.entries])

    def test_duplicate_mmsi_is_rejected_because_it_would_unsettle_the_order(self):
        duplicate = [
            ScoredCandidate(mmsi=V001, vessel_id=None, name="A", vessel_type="x",
                            total=1.0),
            ScoredCandidate(mmsi=V001, vessel_id=None, name="B", vessel_type="x",
                            total=2.0),
        ]
        with self.assertRaises(ValueError):
            rank_candidates(duplicate)

    def test_an_empty_candidate_set_ranks_without_error(self):
        result = rank_candidates([]).to_dict()
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["tieGroups"], [])



class TestScoringConfig(unittest.TestCase):
    """Engine thresholds are configurable, reported, and kept in step with the filter."""

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            ScoringConfig(spatial_falloff_km=0.0)
        with self.assertRaises(ValueError):
            ScoringConfig(gap_relevance_cap=1.5)

    def test_config_describes_the_thresholds_it_owns(self):
        described = ScoringConfig().describe()
        self.assertEqual(set(described), {"spatialFalloffKm", "gapRelevanceCap"})
        self.assertEqual(described["spatialFalloffKm"], SPATIAL_FALLOFF_KM)

    def test_the_engine_falloff_matches_the_compatibility_filter_by_default(self):
        payload = pipeline()
        self.assertEqual(payload["config"]["scoring"]["spatialFalloffKm"],
                         payload["config"]["compatibility"]["spatialFalloffKm"])
        self.assertEqual(payload["weights"], DEFAULT_WEIGHTS)

    def test_a_candidate_without_measurements_still_produces_a_full_explanation(self):
        """The engine degrades to explicit zero-point reasons, never to an exception."""
        from app.ais.filtering import CompatibilityAssessment
        from app.ais.gap_analysis import GapAssessment
        from app.behaviour.baseline import BehaviourAssessment
        from app.timeutils import ReleaseWindow, epoch_seconds

        window = ReleaseWindow(start_epoch=epoch_seconds("2026-03-13T10:00:00Z"),
                               end_epoch=epoch_seconds("2026-03-13T18:00:00Z"),
                               start_iso="2026-03-13T10:00:00Z",
                               end_iso="2026-03-13T18:00:00Z")
        evidence = CandidateEvidence(
            mmsi="999999999", vessel_id=None, name="EMPTY", vessel_type="unknown",
            compatibility=CompatibilityAssessment(mmsi="999999999"),
            behaviour=BehaviourAssessment(mmsi="999999999"),
            gaps=GapAssessment(mmsi="999999999"), window=window,
        )
        scored = score_candidate(evidence).to_dict()
        self.assertEqual(scored["totalScore"], 0.0)
        self.assertEqual(len(scored["reasons"]), len(FACTOR_KEYS))
        self.assertIsNone(
            scored["factors"]["spatial"]["detail"]["minDistanceKmDuringWindow"])
        json.dumps(scored)


if __name__ == "__main__":
    unittest.main(verbosity=2)

