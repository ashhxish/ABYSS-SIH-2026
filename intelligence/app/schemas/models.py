"""ABYSS - Pydantic schemas for the intelligence service.

Adheres to:
  * Pydantic v2 conventions
  * extra="allow" on all models for extensibility
  * Standard envelope fields: `dataSource: str` and `warnings: List[str]`
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class BaseResponse(BaseModel):
    """Universal envelope base for all ABYSS intelligence responses."""

    model_config = ConfigDict(extra="allow")

    dataSource: str = Field(
        ...,
        description="Explicit provenance / data source attribution for transparency",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Operational caveats, degraded state notes, or data warnings",
    )


class HealthResponse(BaseResponse):
    status: str = Field("ok", description="Service operational status")
    service: str = Field("abyss-intelligence", description="Service identifier")
    dataMode: str = Field("demo", description="Current execution mode ('demo' or 'live')")
    demoCaseId: str = Field("CASE-001", description="Identifier of default bundled demo case")


class DataSourceItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    kind: str
    mode: str
    synthetic: bool
    description: str


class DataSourcesResponse(BaseResponse):
    dataMode: str
    demo: bool
    sources: List[DataSourceItem]


class DetectResponse(BaseResponse):
    detection: Dict[str, Any] = Field(..., description="Observation & characterisation payload")


class CharacterizeResponse(BaseResponse):
    characterisation: Dict[str, Any] = Field(..., description="Polygon metrics & bounding box")


class HindcastResponse(BaseResponse):
    origin: Dict[str, Any] = Field(..., description="Backward drift candidate origin region")


class CleanAisResponse(BaseResponse):
    cleaning: Dict[str, Any] = Field(..., description="Cleaning summary, statistics, and record counts")


class TrajectoryResponse(BaseResponse):
    trajectories: Dict[str, Any] = Field(..., description="Reconstructed trajectories and fleet statistics")


class FilterResponse(BaseResponse):
    filter: Dict[str, Any] = Field(..., description="Spatiotemporal compatibility filter results")


class BehaviourResponse(BaseResponse):
    behaviour: Dict[str, Any] = Field(..., description="Speed and heading anomaly baseline results")


class GapResponse(BaseResponse):
    gaps: Dict[str, Any] = Field(..., description="Structural AIS transponder gap analysis")


class Sentinel1Response(BaseResponse):
    observation: Dict[str, Any] = Field(..., description="Real Sentinel-1 SatelliteObservation contract")
    geometry: Dict[str, Any] = Field(..., description="Spill polygon/MultiPolygon in source CRS coordinates")
    result: Dict[str, Any] = Field(..., description="Inference statistics, regions, model provenance")
    previews: Optional[Dict[str, Any]] = Field(None, description="Actual raster preview layers (VV, VH, composite, mask overlay)")



class RealAisAnalyzeResponse(BaseResponse):
    """REAL NOAA AIS analysis result.

    Always carries ``temporalMatchAvailable = False``: the real Sentinel-1 scene
    has no trustworthy acquisition timestamp, so no temporal correlation with
    the SAR scene is asserted and no vessel is attributed responsibility.
    """

    label: str = Field(..., description="Integration-case label, e.g. REAL AIS INTEGRATION - TEMPORAL MATCH PENDING")
    realAis: bool = Field(True, description="True: derived from a real AIS extract, never synthetic")
    source: Dict[str, Any] = Field(..., description="Verified provenance of the real AIS extract")
    temporalMatchAvailable: bool = Field(False, description="Always false in this phase")
    temporalMatchReason: str = Field(..., description="Why temporal correlation is unavailable")
    rawRecordCount: int = Field(..., description="Raw AIS rows in the extract")
    acceptedRecordCount: int = Field(..., description="Rows accepted by Phase-19 contract validation")
    rejectedRecordCount: int = Field(..., description="Rows rejected by Phase-19 contract validation")
    warningCount: int = Field(..., description="Phase-19 validation warnings raised")
    uniqueMmsiCount: int = Field(..., description="Distinct MMSI among accepted records")
    filteredRecordCount: int = Field(..., description="Cleaned records inside the spatial region")
    vesselCount: int = Field(..., description="Vessels with at least one position inside the spatial region")
    trajectoryCount: int = Field(..., description="Real vessel tracks reconstructed from the full extract")
    gapCount: int = Field(..., description="AIS transmission gaps detected across those tracks")
    spatialFilterApplied: bool = Field(..., description="Whether a bounding-box selection was applied")
    spatialBBox: Optional[List[float]] = Field(None, description="Applied west/south/east/north box")
    spatialMatchCount: int = Field(..., description="Positions inside the spatial region")
    vessels: List[Dict[str, Any]] = Field(default_factory=list, description="Vessel-level tracks/features inside the region")
    analysis: Dict[str, Any] = Field(..., description="Ingestion, cleaning, trajectory, spatial and data-quality detail")


class RealAisAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    sourcePath: Optional[str] = Field(
        None,
        description="Real AIS CSV path; defaults to ABYSS_REAL_AIS_CSV or ~/SIH/real_ais/ais_sample.csv",
    )
    bbox: Optional[List[float]] = Field(
        None,
        description="west/south/east/north selection box; defaults to the real Sentinel-1 scene bounds",
    )
    spatialFilter: bool = Field(
        True,
        description="Apply bounding-box selection (spatial only; never a temporal match)",
    )
    startTime: Optional[str] = Field(
        None,
        description="Optional ISO-8601 lower bound selecting records inside the extract",
    )
    endTime: Optional[str] = Field(
        None,
        description="Optional ISO-8601 upper bound selecting records inside the extract",
    )
    maxRecords: Optional[int] = Field(
        None,
        ge=1,
        description="Optional cap on accepted records carried into cleaning/trajectory reconstruction",
    )
    includeVessels: bool = Field(True, description="Include vessel-level track summaries")


class ScoreResponse(BaseResponse):
    scoring: Dict[str, Any] = Field(..., description="Multi-factor ranked candidate vessels")


class InvestigateResponse(BaseResponse):
    investigation: Dict[str, Any] = Field(..., description="End-to-end evidence pipeline synthesis")


# Request schemas

class WeightsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    spatial: Optional[float] = Field(None, ge=0.0)
    gap: Optional[float] = Field(None, ge=0.0)
    trajectory: Optional[float] = Field(None, ge=0.0)
    behaviour: Optional[float] = Field(None, ge=0.0)
    temporal: Optional[float] = Field(None, ge=0.0)


class CleanAisRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    includeRecords: bool = Field(
        False,
        description="Whether to return individual cleaned records in addition to summary counts",
    )


class InvestigateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    weights: Optional[WeightsRequest] = Field(
        None,
        description="Optional custom weights for scoring evidence factors",
    )


# ---------------------------------------------------------------------------
# Real Metocean & Drift Simulation (Phase 22)
# ---------------------------------------------------------------------------

class DriftSimulationRequest(BaseModel):
    """Request for real environmental drift simulation (backward or forward)."""
    origin_lat: float = Field(..., description="Latitude of slick or release point")
    origin_lon: float = Field(..., description="Longitude of slick or release point")
    reference_time_iso: Optional[str] = Field(
        None,
        description="Observation or release time in ISO-8601. REQUIRED. Simulation will be rejected if null/empty."
    )
    direction: str = Field("backward", description="'backward' (hindcast origin) or 'forward' (forecast footprint)")
    duration_hours: float = Field(6.0, ge=0.1, le=168.0, description="Simulation duration in hours")
    step_seconds: float = Field(300.0, ge=10.0, le=3600.0, description="Integration step in seconds")
    windage_ensemble: Optional[List[float]] = Field(
        None,
        description="Optional list of windage values (e.g. [0.02, 0.035, 0.05])"
    )
    currents_path: Optional[str] = Field(None, description="Optional path to NOAA currents NetCDF")
    wind_table_path: Optional[str] = Field(None, description="Optional path to NDBC wind text table")


class DriftSimulationResponse(BaseModel):
    """Response containing particle trajectories, origin/forecast region, and provenance."""
    direction: str
    reference_time_iso: str
    duration_hours: float
    step_seconds: float
    particle_count: int
    centroid: Dict[str, float]
    spread_radius_km: float
    uncertainty_polygon: List[List[float]]
    windage_ensemble: List[float]
    trajectories: List[Dict[str, Any]]
    provenance: Dict[str, Any]
    notes: List[str]
    warnings: List[str]
