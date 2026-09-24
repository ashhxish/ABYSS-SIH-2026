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
