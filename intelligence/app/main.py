"""ABYSS Intelligence Service - FastAPI Application.

Provides REST endpoints for satellite slick observation, AIS cleaning,
trajectory reconstruction, backward drift hindcast, behavior baselines,
transponder gap analysis, multi-factor scoring, and end-to-end investigation.
"""
from __future__ import annotations

from pathlib import Path
import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    DriftSimulationRequest,
    DriftSimulationResponse,
)
from app.hindcast.metocean import (
    load_noaa_currents_netcdf,
    load_ndbc_table,
    find_nearest_wind,
)
from app.hindcast.drift import run_drift_simulation
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app import config as app_config
from app.ais.cleaning import clean_demo_case
from app.ais.filtering import assess_compatibility
from app.ais.gap_analysis import analyse_gaps
from app.ais.trajectory import build_trajectories_from_cleaning
from app.behaviour.baseline import assess_behaviour
from app.detection import DemoSatelliteProvider, characterise_polygon, detect_slick, observe_case
from app.hindcast.origin import OriginConfig, estimate_origin
from app.investigation import load_case_inputs, run_investigation
from app.schemas import (
    BaseResponse,
    BehaviourResponse,
    CharacterizeResponse,
    CleanAisRequest,
    CleanAisResponse,
    DataSourceItem,
    DataSourcesResponse,
    DetectResponse,
    FilterResponse,
    GapResponse,
    HealthResponse,
    HindcastResponse,
    InvestigateRequest,
    InvestigateResponse,
    RealAisAnalyzeRequest,
    RealAisAnalyzeResponse,
    ScoreResponse,
    Sentinel1Response,
    TrajectoryResponse,
    WeightsRequest,
)
from app.scoring.engine import FACTOR_KEYS, EvidenceWeights
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("abyss.intelligence")

app = FastAPI(
    title="ABYSS Intelligence Service",
    description="Maritime Dark Vessel and Oil Spill Attribution Intelligence API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    settings = app_config.get_settings()
    path_warnings = settings.validate_paths()
    return HealthResponse(
        status="ok",
        service="abyss-intelligence",
        dataMode=settings.data_mode,
        demoCaseId=settings.demo_case_id,
        dataSource=f"Configuration ({settings.data_mode} mode)",
        warnings=path_warnings,
    )


@app.get("/data-sources", response_model=DataSourcesResponse)
def get_data_sources() -> DataSourcesResponse:
    settings = app_config.get_settings()
    sources = [
        DataSourceItem(
            name="DemoSatelliteProvider",
            kind="satellite",
            mode=settings.data_mode,
            synthetic=True,
            description="Bundled synthetic SAR polygon with pre-computed geometry.",
        ),
        DataSourceItem(
            name="DemoAISProvider",
            kind="ais",
            mode=settings.data_mode,
            synthetic=True,
            description="Bundled synthetic AIS positional reports (3,666 raw records).",
        ),
        DataSourceItem(
            name="DemoEnvironmentalProvider",
            kind="environmental",
            mode=settings.data_mode,
            synthetic=True,
            description="Synthetic ECMWF/HYCOM style steady drift & wind fields.",
        ),
    ]
    return DataSourcesResponse(
        dataMode=settings.data_mode,
        demo=(settings.data_mode == "demo"),
        sources=sources,
        dataSource="Bundled demo dataset manifest",
        warnings=settings.validate_paths(),
    )


@app.post("/detect", response_model=DetectResponse)
def post_detect() -> DetectResponse:
    settings = app_config.get_settings()
    try:
        detection = observe_case(settings.demo_case_dir)
        return DetectResponse(
            dataSource=detection.get("dataSource", "DemoSatelliteProvider"),
            warnings=detection.get("warnings", []),
            detection=detection,
        )
    except Exception as exc:
        logger.exception("Slick detection failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Slick detection failed: {exc}",
        ) from exc


@app.post("/characterize", response_model=CharacterizeResponse)
def post_characterize() -> CharacterizeResponse:
    settings = app_config.get_settings()
    try:
        provider = DemoSatelliteProvider.for_case(settings.demo_case_dir)
        scenario = provider.fetch()
        char = characterise_polygon(scenario)
        warnings: List[str] = []
        if scenario.get("synthetic"):
            warnings.append("characterisation computed from synthetic demonstration polygon")
        return CharacterizeResponse(
            dataSource=provider.label,
            warnings=warnings,
            characterisation=char,
        )
    except Exception as exc:
        logger.exception("Characterisation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Polygon characterisation failed: {exc}",
        ) from exc


@app.post("/hindcast", response_model=HindcastResponse)
def post_hindcast() -> HindcastResponse:
    settings = app_config.get_settings()
    try:
        inputs = load_case_inputs(settings)
        origin = estimate_origin(
            slick_ring=inputs["slickRing"],
            observed_iso=inputs["observedAt"],
            window=inputs["window"],
            field=inputs["field"],
            config=OriginConfig(),
        )
        origin_dict = origin.to_dict()
        return HindcastResponse(
            dataSource=(
                "Hindcast backwards drift "
                f"({origin.sample_count} particle snapshots from {origin.seed_count} seeds)"
            ),
            warnings=origin_dict.get("warnings", []),
            origin=origin_dict,
        )
    except Exception as exc:
        logger.exception("Hindcast failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backward drift hindcast failed: {exc}",
        ) from exc


@app.post("/ais/clean", response_model=CleanAisResponse)
def post_ais_clean(request: Optional[CleanAisRequest] = None) -> CleanAisResponse:
    settings = app_config.get_settings()
    req = request or CleanAisRequest()
    try:
        result = clean_demo_case(settings)
        payload = result.to_dict()
        warnings = list(payload.get("warnings", []))
        if not req.includeRecords:
            payload["records"] = []
            warnings.append("individual records omitted from response; set includeRecords=true to include")
        return CleanAisResponse(
            dataSource=payload.get("dataSource", "DemoAISProvider"),
            warnings=warnings,
            cleaning=payload,
        )
    except Exception as exc:
        logger.exception("AIS cleaning failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AIS cleaning failed: {exc}",
        ) from exc


@app.post("/ais/trajectory", response_model=TrajectoryResponse)
def post_ais_trajectory() -> TrajectoryResponse:
    settings = app_config.get_settings()
    try:
        cleaning = clean_demo_case(settings)
        bundle = build_trajectories_from_cleaning(cleaning)
        payload = bundle.to_dict()
        return TrajectoryResponse(
            dataSource=payload.get("dataSource", "DemoAISProvider"),
            warnings=payload.get("warnings", []),
            trajectories=payload,
        )
    except Exception as exc:
        logger.exception("Trajectory reconstruction failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Trajectory reconstruction failed: {exc}",
        ) from exc


@app.post("/ais/filter", response_model=FilterResponse)
def post_ais_filter() -> FilterResponse:
    settings = app_config.get_settings()
    try:
        inputs = load_case_inputs(settings)
        origin = estimate_origin(
            slick_ring=inputs["slickRing"],
            observed_iso=inputs["observedAt"],
            window=inputs["window"],
            field=inputs["field"],
            config=OriginConfig(),
        )
        cleaning = clean_demo_case(settings)
        trajectories = build_trajectories_from_cleaning(cleaning)

        assessments = {}
        warnings: List[str] = list(trajectories.warnings)
        for traj in trajectories.trajectories:
            ass = assess_compatibility(traj, origin, inputs["window"])
            assessments[traj.mmsi] = ass.to_dict()
            warnings.extend(ass.warnings)

        return FilterResponse(
            dataSource=trajectories.to_dict().get("dataSource", "DemoAISProvider"),
            warnings=list(dict.fromkeys(warnings)),
            filter={
                "vesselCount": len(assessments),
                # CompatibilityAssessment.to_dict() nests the pass/fail booleans
                # under "filters"; insideRegionDuringWindow is the plain observation
                # (this endpoint measures it, it never assumes it).
                "candidatesInsideRegionDuringWindow": sum(
                    1 for a in assessments.values() if a.get("insideRegionDuringWindow")
                ),
                "candidatesPassingSpatial": sum(
                    1 for a in assessments.values() if a.get("filters", {}).get("spatial")
                ),
                "candidatesPassingTemporal": sum(
                    1 for a in assessments.values() if a.get("filters", {}).get("temporal")
                ),
                "candidatesPassingTrajectory": sum(
                    1 for a in assessments.values() if a.get("filters", {}).get("trajectory")
                ),
                "assessments": assessments,
            },
        )
    except Exception as exc:
        logger.exception("Compatibility filter failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Compatibility filter failed: {exc}",
        ) from exc


@app.post("/ais/behaviour", response_model=BehaviourResponse)
def post_ais_behaviour() -> BehaviourResponse:
    settings = app_config.get_settings()
    try:
        inputs = load_case_inputs(settings)
        origin = estimate_origin(
            slick_ring=inputs["slickRing"],
            observed_iso=inputs["observedAt"],
            window=inputs["window"],
            field=inputs["field"],
            config=OriginConfig(),
        )
        cleaning = clean_demo_case(settings)
        trajectories = build_trajectories_from_cleaning(cleaning)

        results = {}
        warnings: List[str] = list(trajectories.warnings)
        for traj in trajectories.trajectories:
            ass = assess_compatibility(traj, origin, inputs["window"])
            b_ass = assess_behaviour(traj, inputs["window"], ass.inside_region_during_window)
            results[traj.mmsi] = b_ass.to_dict()

        return BehaviourResponse(
            dataSource=trajectories.to_dict().get("dataSource", "DemoAISProvider"),
            warnings=list(dict.fromkeys(warnings)),
            behaviour={"vesselCount": len(results), "assessments": results},
        )
    except Exception as exc:
        logger.exception("Behaviour baseline failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Behaviour baseline failed: {exc}",
        ) from exc


@app.post("/ais/gaps", response_model=GapResponse)
def post_ais_gaps() -> GapResponse:
    settings = app_config.get_settings()
    try:
        inputs = load_case_inputs(settings)
        origin = estimate_origin(
            slick_ring=inputs["slickRing"],
            observed_iso=inputs["observedAt"],
            window=inputs["window"],
            field=inputs["field"],
            config=OriginConfig(),
        )
        cleaning = clean_demo_case(settings)
        trajectories = build_trajectories_from_cleaning(cleaning)

        gap_results = {}
        for traj in trajectories.trajectories:
            analysis = analyse_gaps(traj, origin, inputs["window"])
            gap_results[traj.mmsi] = analysis.to_dict()

        return GapResponse(
            dataSource=trajectories.to_dict().get("dataSource", "DemoAISProvider"),
            warnings=list(dict.fromkeys(trajectories.warnings)),
            gaps={"vesselCount": len(gap_results), "assessments": gap_results},
        )
    except Exception as exc:
        logger.exception("Gap analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gap analysis failed: {exc}",
        ) from exc


class WeightValidationError(ValueError):
    """The submitted weights are invalid (a 400, not an internal 500).

    Scoped to its own type so a ValueError raised deeper inside the pipeline is
    still reported honestly as a server error instead of being mislabelled as a
    bad request.
    """


def _build_evidence_weights(req_weights: Optional[WeightsRequest]) -> Optional[EvidenceWeights]:
    """Turn a request body into EvidenceWeights, or None for the documented defaults.

    Unknown factor names are rejected explicitly (HTTP 400 by the callers) rather
    than being silently dropped, so a typo in a weight name can never change the
    ranking without the caller noticing.
    """
    if not req_weights:
        return None
    raw = req_weights.model_dump(exclude_unset=True, exclude_none=True)
    if not raw:
        return None
    unknown = sorted(set(raw) - set(FACTOR_KEYS))
    if unknown:
        raise WeightValidationError(
            f"unknown evidence factor(s) {unknown}; expected any of {list(FACTOR_KEYS)}"
        )
    try:
        return EvidenceWeights(**raw)
    except ValueError as exc:  # negative weight, zero total, ...
        raise WeightValidationError(f"invalid evidence weights: {exc}") from exc


@app.post("/score", response_model=ScoreResponse)
def post_score(request: Optional[InvestigateRequest] = None) -> ScoreResponse:
    settings = app_config.get_settings()
    try:
        weights = _build_evidence_weights(request.weights if request else None)
        investigation = run_investigation(settings=settings, weights=weights)
        inv_dict = investigation.to_dict()
        ranking = inv_dict.get("ranking", {})
        return ScoreResponse(
            dataSource=inv_dict.get("source", {}).get("provider", "DemoAISProvider"),
            warnings=inv_dict.get("warnings", []),
            scoring={
                "weights": inv_dict.get("weights", {}),
                "ranking": ranking,
                "candidates": inv_dict.get("candidates", []),
            },
        )
    except WeightValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Scoring failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Candidate scoring failed: {exc}",
        ) from exc



class Sentinel1IngestRequest(BaseModel):
    """Request body for real Sentinel-1 ingestion (Phase 1, no downloading)."""

    model_config = ConfigDict(extra="allow")

    scenePath: str = Field(
        ...,
        description="Local Sentinel-1 GeoTIFF path (VV+VH). No downloading is performed.",
    )
    modelPath: Optional[str] = Field(
        None,
        description="Optional explicit checkpoint path; defaults to ABYSS_SENTINEL1_MODEL_PATH.",
    )
    caseId: str = Field(
        "CASE-REAL-001",
        description="Case identifier attached to the real SatelliteObservation.",
    )
    includePreviews: bool = Field(
        True,
        description="Whether to generate browser-safe raster previews (VV, VH, composite, mask overlay).",
    )


@app.post("/sentinel1/detect", response_model=Sentinel1Response)
def post_sentinel1_detect(request: Sentinel1IngestRequest) -> Sentinel1Response:
    """Run REAL Sentinel-1 U-Net inference and return the observation.

    The checkpoint resolves through ``ABYSS_SENTINEL1_MODEL_PATH`` (or the
    explicit ``modelPath``). A missing checkpoint is an honest 500 - a real
    inference NEVER silently falls back to the synthetic CASE-001 scene.
    """
    from app.detection.sentinel1 import (
        Sentinel1Error,
        detect_scene,
        generate_preview_layers,
        result_warnings,
        to_satellite_observation,
    )

    try:
        result = detect_scene(request.scenePath, request.modelPath)
        observation = to_satellite_observation(result, case_id=request.caseId)
        warnings = result_warnings(result)
        previews = None
        if request.includePreviews:
            previews = generate_preview_layers(request.scenePath, result.mask)
        return Sentinel1Response(
            dataSource="Sentinel1UNetAdapter",
            warnings=warnings,
            observation=observation.to_dict(),
            geometry=observation.geometry,
            result=result.to_dict(),
            previews=previews,
        )
    except Sentinel1Error as exc:
        logger.exception("Real Sentinel-1 inference failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Real Sentinel-1 inference failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Real Sentinel-1 inference failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Real Sentinel-1 inference failed: {exc}",
        ) from exc


@app.post("/ais/real/analyze", response_model=RealAisAnalyzeResponse)
def post_ais_real_analyze(
    request: Optional[RealAisAnalyzeRequest] = None,
) -> RealAisAnalyzeResponse:
    """Analyse a REAL historical AIS extract with the EXISTING ABYSS AIS engine.

    SPATIAL + DATA-QUALITY ANALYSIS ONLY.  The real Sentinel-1 scene has no
    trustworthy acquisition timestamp, so this endpoint always reports
    ``temporalMatchAvailable = false`` and never attributes slick
    responsibility to a vessel.
    """
    from app.ais.real_ais import RealAisError, analyse_real_ais

    req = request or RealAisAnalyzeRequest()
    try:
        result = analyse_real_ais(
            source_path=req.sourcePath,
            bbox=req.bbox,
            start_time=req.startTime,
            end_time=req.endTime,
            max_records=req.maxRecords,
            spatial_filter=req.spatialFilter,
            include_vessels=req.includeVessels,
        )
    except RealAisError as exc:
        logger.exception("Real AIS analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Real AIS analysis failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Real AIS analysis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Real AIS analysis failed: {exc}",
        ) from exc

    return RealAisAnalyzeResponse(
        dataSource=result["source"]["provider"],
        warnings=list(result.get("warnings", [])),
        label=result["label"],
        realAis=result["realAis"],
        source=result["source"],
        temporalMatchAvailable=result["temporalMatchAvailable"],
        temporalMatchReason=result["temporalMatchReason"],
        rawRecordCount=result["rawRecordCount"],
        acceptedRecordCount=result["acceptedRecordCount"],
        rejectedRecordCount=result["rejectedRecordCount"],
        warningCount=result["warningCount"],
        uniqueMmsiCount=result["uniqueMmsiCount"],
        filteredRecordCount=result["filteredRecordCount"],
        vesselCount=result["vesselCount"],
        trajectoryCount=result["trajectoryCount"],
        gapCount=result["gapCount"],
        spatialFilterApplied=result["spatialFilterApplied"],
        spatialBBox=result["spatialBBox"],
        spatialMatchCount=result["spatialMatchCount"],
        vessels=result["vessels"],
        analysis=result["analysis"],
    )


@app.post("/investigate", response_model=InvestigateResponse)
def post_investigate(request: Optional[InvestigateRequest] = None) -> InvestigateResponse:
    settings = app_config.get_settings()
    try:
        weights = _build_evidence_weights(request.weights if request else None)
        investigation = run_investigation(settings=settings, weights=weights)
        inv_dict = investigation.to_dict()
        return InvestigateResponse(
            dataSource=inv_dict.get("source", {}).get("provider", "DemoAISProvider"),
            warnings=inv_dict.get("warnings", []),
            investigation=inv_dict,
        )
    except WeightValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Investigation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Investigation failed: {exc}",
        ) from exc


@app.post("/drift/real/simulate", response_model=DriftSimulationResponse)
def post_real_drift_simulate(request: DriftSimulationRequest) -> DriftSimulationResponse:
    """Run real metocean drift simulation (backward or forward).

    Observation/release time is strictly REQUIRED. ABYSS forbids simulating
    drift without an explicit timestamp; processed_at or current time will
    never be substituted.
    """
    if not request.reference_time_iso or not request.reference_time_iso.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "reference_time_iso is REQUIRED for real drift simulation. "
                "ABYSS refuses to simulate drift without an explicit observation timestamp."
            ),
        )

    # Resolve currents NetCDF path
    currents_path = (
        Path(request.currents_path)
        if request.currents_path
        else Path("/home/ashish/SIH/real_metocean/noaa_currents/currents_20240529.nc")
    )
    if not currents_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ocean currents NetCDF not found: {currents_path}",
        )

    # Optional wind table
    wind_record = None
    if request.wind_table_path:
        wpath = Path(request.wind_table_path)
        if wpath.is_file():
            try:
                from datetime import datetime, timezone
                target_dt = datetime.fromisoformat(request.reference_time_iso.replace("Z", "+00:00"))
                records = load_ndbc_table(wpath)
                wind_record = find_nearest_wind(records, target_dt.timestamp())
            except Exception as e:
                logger.warning("Could not match wind observation: %s", e)

    try:
        field, prov = load_noaa_currents_netcdf(currents_path, wind_record=wind_record)
        res = run_drift_simulation(
            field=field,
            origin_lat=request.origin_lat,
            origin_lon=request.origin_lon,
            reference_time_iso=request.reference_time_iso,
            direction=request.direction,
            duration_hours=request.duration_hours,
            step_seconds=request.step_seconds,
            windage_ensemble=request.windage_ensemble,
            provenance_meta=prov.to_dict(),
        )
        data = res.to_dict()
        return DriftSimulationResponse(**data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Real drift simulation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Drift simulation failed: {exc}",
        ) from exc
