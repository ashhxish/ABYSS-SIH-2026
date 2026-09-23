"""ABYSS - evidence pipeline orchestrator (Phases 5-11 assembled).

PURPOSE
    Run the whole attribution intelligence pipeline for one case and return a
    single explainable result:

        cleaning (Phase 3) -> trajectories (Phase 4)
        -> origin hindcast (slick + environmental field, Phase 11)
        -> compatibility (Phases 5-7) -> behaviour (Phase 8) -> gaps (Phase 9)
        -> evidence scoring + ranking (Phase 10)

    Every stage's per-vessel assessment travels with its ranking entry, so an
    investigator can audit WHY a candidate sits where it does.

READING THE RESULT
    * origin.region          reconstructed GeoJSON region + confidence (never a point)
    * origin.releaseWindow   candidate-window prior, reported with provenance
    * ranking.entries[]      rank, total, per-factor points, reasons,
                             counterfactual, and the raw assessments behind them
    * weights                the configured evidence weights actually used
    * limitations            prototype caveats from docs/methodology.md

WHAT THIS MODULE NEVER DOES
    It never reads the scenario answer key (demo_origin_expected.json) or the
    expected-ranking fixture - those belong to the test suite only. The dataset
    disclaimer travels verbatim in the output, and no field asserts guilt.

CLI
    cd intelligence
    ../.venv/bin/python -m app.investigation
    ../.venv/bin/python -m app.investigation --json /tmp/investigation.json
    ../.venv/bin/python -m app.investigation --weight-spatial 40 --weight-gap 20 --quiet
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

if __package__ in (None, ""):  # executed directly as a script
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ais.cleaning import clean_demo_case
from app.ais.filtering import CompatibilityConfig, assess_compatibility
from app.ais.gap_analysis import GapAnalysisConfig, analyse_gaps
from app.ais.trajectory import build_trajectories_from_cleaning
from app.behaviour.baseline import BehaviourConfig, assess_behaviour
from app.config import Settings, get_settings
from app.geo import distance_to_ring_km
from app.hindcast.environmental import EnvironmentalField
from app.hindcast.origin import OriginConfig, estimate_origin
from app.scoring.engine import (CandidateEvidence, EvidenceWeights, ScoringConfig,
                                score_candidate)
from app.scoring.ranking import rank_candidates
from app.timeutils import ReleaseWindow, epoch_seconds

MODULE_VERSION = "1.0.0"

DEFAULT_DISCLAIMER = (
    "ABYSS provides analytical evidence for investigation support. Candidate ranking "
    "does not establish legal responsibility."
)

LIMITATIONS = [
    "prototype drift model: forward-Euler integration of a steady demo field, "
    "not a validated ocean model (docs/methodology.md)",
    "the windage coefficient is a prototype value, configurable, not scientifically "
    "calibrated",
    "the release window is a candidate-window prior supplied with the case; the "
    "origin REGION is what the product reconstructs from slick + environmental data",
    "thresholds (falloff distance, feasibility margin, anomaly references) are "
    "prototype choices reported in the output - they are not physical constants",
    "AIS coverage is uneven by nature: a gap is ambiguous and never, on its own, "
    "evidence against a vessel",
    "the origin is a REGION with uncertainty - ABYSS never publishes a single-point "
    "origin and never a probability of guilt",
    "candidate ranking orders evidence for investigation support; it does not "
    "establish legal responsibility",
    "this dataset is synthetic demonstration data and describes no real vessel, "
    "voyage, spill or incident",
]


class InvestigationError(RuntimeError):
    """Raised when case inputs are missing or inconsistent."""


def load_case_inputs(settings: Optional[Settings] = None,
                     case_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load case JSON, slick, environmental field and the candidate window.

    These are the only non-AIS inputs the pipeline reads. The answer-key files
    of the demo bundle are deliberately NOT loaded here - ever.
    """
    settings = settings or get_settings()
    directory = Path(case_dir) if case_dir is not None else settings.demo_case_dir
    case_path = directory / f"{directory.name}.json"
    if not case_path.exists():
        raise InvestigationError(
            f"case file not found at {case_path}; regenerate the demo bundle with "
            "python3 intelligence/data/demo/generate_case_001.py"
        )
    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvestigationError(f"case file {case_path} is not valid JSON: {exc}") from exc

    try:
        release = case["origin"]["releaseWindow"]
        window = ReleaseWindow(
            start_epoch=epoch_seconds(release["start"]),
            end_epoch=epoch_seconds(release["end"]),
            start_iso=release["start"], end_iso=release["end"],
            source="candidate release window (case input prior)",
        )
        observed_at = case["observation"]["observedAt"]
    except (KeyError, TypeError, ValueError) as exc:
        raise InvestigationError(
            f"case file {case_path} must define origin.releaseWindow and "
            f"observation.observedAt as ISO-8601 timestamps: {exc}"
        ) from exc

    slick_name = case.get("observation", {}).get("slickFile", "demo_slick.json")
    slick_path = directory / slick_name
    if not slick_path.exists():
        raise InvestigationError(f"slick file not found at {slick_path}")
    try:
        slick = json.loads(slick_path.read_text(encoding="utf-8"))
        geometry = slick["geometry"]
        if geometry["type"] == "MultiPolygon":
            ring = geometry["coordinates"][0][0]
        else:
            ring = geometry["coordinates"][0]
        if len(ring) < 4:
            raise ValueError("slick ring has fewer than 4 positions")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise InvestigationError(f"slick file {slick_path} unusable: {exc}") from exc

    field_rel = case.get("environment", {}).get("file",
                                                "environmental/demo_environmental_field.json")
    environmental = EnvironmentalField.load(directory / field_rel)

    vessels_by_mmsi = {str(v.get("mmsi")): v
                       for v in case.get("vessels", []) if v.get("mmsi") is not None}

    return {
        "caseId": case.get("caseId"),
        "case": case,
        "caseDir": directory,
        "window": window,
        "observedAt": observed_at,
        "slick": slick,
        "slickRing": [(float(p[0]), float(p[1])) for p in ring],
        "field": environmental,
        "vesselsByMmsi": vessels_by_mmsi,
        "disclaimer": str(case.get("disclaimer") or DEFAULT_DISCLAIMER),
        "datasetLabel": case.get("datasetLabel"),
        "synthetic": bool(case.get("synthetic", True)),
    }


@dataclass
class InvestigationResult:
    """The full pipeline output: origin estimate + ranked, explained candidates."""

    case_id: Optional[str]
    dataset_label: Optional[str]
    synthetic: bool
    disclaimer: str
    observed_at: str
    origin: OriginEstimate
    ranking: RankingResult
    weights: EvidenceWeights
    scoring_config: ScoringConfig
    compatibility_config: CompatibilityConfig
    behaviour_config: BehaviourConfig
    gap_config: GapAnalysisConfig
    assessments: Dict[str, Dict[str, Any]] = dataclass_field(default_factory=dict)
    statistics: Dict[str, Any] = dataclass_field(default_factory=dict)
    warnings: List[str] = dataclass_field(default_factory=list)
    notes: List[str] = dataclass_field(default_factory=list)
    limitations: List[str] = dataclass_field(default_factory=lambda: list(LIMITATIONS))
    source: Dict[str, Any] = dataclass_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-ready payload: each entry carries its raw assessments too."""
        ranking_payload = self.ranking.to_dict()
        entries = []
        for entry in self.ranking.entries:
            payload = entry.to_dict()
            payload.update(self.assessments.get(entry.mmsi, {}))
            entries.append(payload)
        ranking_payload["entries"] = entries
        return {
            "module": "investigation",
            "moduleVersion": MODULE_VERSION,
            "caseId": self.case_id,
            "datasetLabel": self.dataset_label,
            "synthetic": self.synthetic,
            "disclaimer": self.disclaimer,
            "observedAt": self.observed_at,
            "origin": self.origin.to_dict(),
            "weights": self.weights.describe(),
            "config": {
                "scoring": self.scoring_config.describe(),
                "compatibility": self.compatibility_config.describe(),
                "behaviour": self.behaviour_config.describe(),
                "gapAnalysis": self.gap_config.describe(),
            },
            "statistics": dict(self.statistics),
            "ranking": ranking_payload,
            "source": dict(self.source),
            "warnings": list(self.warnings),
            "notes": list(self.notes),
            "limitations": list(self.limitations),
        }


def run_investigation(
    settings: Optional[Settings] = None,
    *,
    case_dir: Optional[Path] = None,
    weights: Optional[EvidenceWeights] = None,
    origin_config: Optional[OriginConfig] = None,
    compatibility_config: Optional[CompatibilityConfig] = None,
    behaviour_config: Optional[BehaviourConfig] = None,
    gap_config: Optional[GapAnalysisConfig] = None,
    scoring_config: Optional[ScoringConfig] = None,
) -> InvestigationResult:
    """Run the full pipeline for the demo case (or a supplied case directory).

    Deterministic: identical inputs and configuration give identical output.
    Raises InvestigationError when inputs are unusable - a silently wrong input
    is worse than a crash.
    """
    settings = settings or get_settings()
    weights = weights or EvidenceWeights()
    origin_cfg = origin_config or OriginConfig()
    compat_cfg = compatibility_config or CompatibilityConfig()
    behav_cfg = behaviour_config or BehaviourConfig()
    gap_cfg = gap_config or GapAnalysisConfig()
    # Keep the engine's spatial falloff identical to the filter's by default.
    score_cfg = scoring_config or ScoringConfig(
        spatial_falloff_km=compat_cfg.spatial_falloff_km)

    inputs = load_case_inputs(settings, case_dir)
    window: ReleaseWindow = inputs["window"]
    cleaning = clean_demo_case(settings)
    trajectories = build_trajectories_from_cleaning(cleaning)
    origin = estimate_origin(inputs["slickRing"], inputs["observedAt"], window,
                              inputs["field"], origin_cfg)

    obs_epoch = origin.observed_epoch
    slick_ring = inputs["slickRing"]
    scored = []
    assessments: Dict[str, Dict[str, Any]] = {}
    warnings: List[str] = list(origin.warnings)
    gaps_judged = 0
    behaviour_flags = 0
    inside_count = 0

    for trajectory in trajectories.trajectories:
        compatibility = assess_compatibility(trajectory, origin, window, compat_cfg)
        behaviour = assess_behaviour(
            trajectory, window, compatibility.inside_region_during_window, behav_cfg)
        gaps = analyse_gaps(trajectory, origin, window, gap_cfg)
        gaps_judged += len(gaps.gaps)
        behaviour_flags += 1 if behaviour.is_anomaly else 0
        inside_count += 1 if compatibility.inside_region_during_window else 0

        meta = inputs["vesselsByMmsi"].get(trajectory.mmsi, {})
        distance_slick: Optional[float] = None
        if trajectory.points:
            nearest = min(trajectory.points,
                          key=lambda p: abs(p.epochSeconds - obs_epoch))
            distance_slick = distance_to_ring_km(
                nearest.latitude, nearest.longitude, slick_ring)

        evidence = CandidateEvidence(
            mmsi=trajectory.mmsi,
            vessel_id=meta.get("vesselId"),
            name=str(meta.get("name") or trajectory.vesselName or trajectory.mmsi),
            vessel_type=str(meta.get("typeLabel") or trajectory.vesselType or "unknown"),
            compatibility=compatibility,
            behaviour=behaviour,
            gaps=gaps,
            window=window,
            distance_to_slick_km=distance_slick,
        )
        scored.append(score_candidate(evidence, weights, score_cfg))
        assessments[trajectory.mmsi] = {
            "compatibility": compatibility.to_dict(),
            "behaviour": behaviour.to_dict(),
            "gapAnalysis": gaps.to_dict(),
        }

    ranking = rank_candidates(scored)
    totals = [entry.total for entry in ranking.entries]
    statistics = {
        "vesselsScored": len(scored),
        "recordsCleaned": len(cleaning.records),
        "insideRegionDuringWindow": inside_count,
        "gapsJudged": gaps_judged,
        "behaviourAnomaliesReported": behaviour_flags,
        "originAreaKm2": round(origin.area_km2, 3),
        "originConfidence": round(origin.confidence, 3),
        "weightsTotal": weights.total,
        "meanScore": round(sum(totals) / len(totals), 3) if totals else 0.0,
        "topCandidateMmsi": ranking.entries[0].mmsi if ranking.entries else None,
        "tieGroupCount": len(ranking.tie_groups()),
    }
    warnings.extend(w for w in cleaning.warnings if w not in warnings)
    if inputs["synthetic"]:
        warnings.append("synthetic demonstration data (DEMO DATA) - not a real incident")
    notes = [
        "inputs: cleaned AIS + case JSON + slick polygon + environmental field; "
        "scenario answer keys are never read by this pipeline",
        "every factor is reported with its reason, including factors that scored 0",
        "equal totals are shown as tie groups - the evidence, not the identifier, "
        "is the result",
    ]
    source = {
        "provider": cleaning.data_source,
        "datasetLabel": inputs["datasetLabel"],
        "caseId": inputs["caseId"],
        "caseDir": str(inputs["caseDir"]),
        "environmentalField": inputs["field"].source_path,
    }

    return InvestigationResult(
        case_id=inputs["caseId"],
        dataset_label=inputs["datasetLabel"],
        synthetic=inputs["synthetic"],
        disclaimer=inputs["disclaimer"],
        observed_at=inputs["observedAt"],
        origin=origin,
        ranking=ranking,
        weights=weights,
        scoring_config=score_cfg,
        compatibility_config=compat_cfg,
        behaviour_config=behav_cfg,
        gap_config=gap_cfg,
        assessments=assessments,
        statistics=statistics,
        warnings=warnings,
        notes=notes,
        source=source,
    )


def _print_summary(payload: Dict[str, Any]) -> None:
    """Compact console view of the JSON payload."""
    ranking = payload["ranking"]
    origin = payload["origin"]
    print(f"case {payload.get('caseId')} ({payload.get('datasetLabel')})")
    print(f"origin region: {origin['region']['areaKm2']:.1f} km2, "
          f"confidence {origin['region']['confidence']:.2f}; release window "
          f"{origin['releaseWindow']['start']} .. {origin['releaseWindow']['end']}")
    print(f"weights: {payload['weights']}")
    print(f"{'rank':>4} {'mmsi':>10} {'score':>7}  candidate")
    for entry in ranking["entries"]:
        tag = f"({entry.get('vesselId') or '-'})"
        print(f"{entry['rank']:>4} {entry['mmsi']:>10} {entry['totalScore']:>7.3f}  "
              f"{tag} {entry['name']}")
    for group in ranking["tieGroups"]:
        print(f"tied score, ordered by MMSI: {', '.join(group)}")
    print(f"disclaimer: {payload['disclaimer']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point. Returns a process exit code (0 = success)."""
    parser = argparse.ArgumentParser(
        prog="app.investigation",
        description="Run the ABYSS evidence pipeline (origin hindcast, compatibility, "
                    "behaviour, AIS gaps, scoring, ranking) for the configured case.")
    parser.add_argument("--json", dest="json_out", default=None,
                        help="write the full result as JSON to this path")
    parser.add_argument("--weight-spatial", dest="weight_spatial", type=float,
                        default=None, help="override the distance-to-origin weight")
    parser.add_argument("--weight-gap", dest="weight_gap", type=float, default=None,
                        help="override the AIS-gap behaviour weight")
    parser.add_argument("--weight-trajectory", dest="weight_trajectory", type=float,
                        default=None, help="override the course-change correlation weight")
    parser.add_argument("--weight-behaviour", dest="weight_behaviour", type=float,
                        default=None, help="override the stop/slow pattern weight")
    parser.add_argument("--weight-temporal", dest="weight_temporal", type=float,
                        default=None, help="override the release-window proximity weight")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress the printed summary")
    args = parser.parse_args(argv)

    overrides = {"spatial": args.weight_spatial, "gap": args.weight_gap,
                 "trajectory": args.weight_trajectory,
                 "behaviour": args.weight_behaviour,
                 "temporal": args.weight_temporal}
    try:
        weights = EvidenceWeights(**{k: v for k, v in overrides.items()
                                     if v is not None})
        result = run_investigation(weights=weights)
    except (InvestigationError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    payload = result.to_dict()
    if args.json_out:
        out = Path(args.json_out)
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        if not args.quiet:
            print(f"wrote {out}")
    if not args.quiet:
        _print_summary(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())