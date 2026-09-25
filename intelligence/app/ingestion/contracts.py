"""ABYSS - Phase 19 normalized input contracts.

These dataclasses are the data-ingestion boundary between (future) real-world
data sources and the ABYSS forensic core:

    SatelliteObservation      -> app.detection.satellite
    AisReport                 -> app.ais.cleaning
    EnvironmentalObservation  -> app.hindcast.environmental

Deliberate scope limits:
  * only concepts the existing core already consumes are represented;
  * no new scientific variables, units or constants are introduced;
  * provenance values are copied from the source, never invented;
  * no core module is imported, subclassed or modified by this package;
  * DEMO MODE is untouched - the adapters can represent the bundled CASE-001
    dataset and the investigation result is unchanged (tests assert this).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "CONTRACT_VERSION",
    "SYNTHETIC_LABEL",
    "ContractError",
    "Provenance",
    "SatelliteObservation",
    "AisReport",
    "EnvironmentalObservation",
    "NormalizedBatch",
]

CONTRACT_VERSION = "1.0.0"
SYNTHETIC_LABEL = "Synthetic Demonstration Dataset"

_MMSI_RE = re.compile(r"^\d{9}$")
_BEARING_HINT = "degrees clockwise from true north in [0, 360)"


class ContractError(ValueError):
    """A record cannot be normalized at all (structural failure)."""


@dataclass(frozen=True)
class Provenance:
    """Where a normalized record came from.

    Every field is copied from the source document. `ingestedAt` is the only
    field the caller may set, and adapters deliberately leave it ``None`` so
    that repeated runs of the deterministic demo remain byte-identical.
    """

    sourceType: str
    sourceName: Optional[str] = None
    sourceFile: Optional[str] = None
    originalId: Optional[str] = None
    synthetic: bool = False
    datasetLabel: Optional[str] = None
    ingestedAt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(asdict(self))

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]], *,
                  sourceType: str = "unknown",
                  sourceFile: Optional[str] = None) -> "Provenance":
        raw = raw or {}
        synthetic = raw.get("synthetic", raw.get("syntheticDataset", False))
        return cls(
            sourceType=str(raw.get("sourceType", sourceType)),
            sourceName=_opt_str(raw.get("sourceName", raw.get("provider"))),
            sourceFile=_opt_str(raw.get("sourceFile", sourceFile)),
            originalId=_opt_str(raw.get("originalId", raw.get("id"))),
            synthetic=bool(synthetic),
            datasetLabel=_opt_str(raw.get("datasetLabel")),
            ingestedAt=_opt_str(raw.get("ingestedAt")),
        )


@dataclass
class SatelliteObservation:
    """A possible oil-slick observation plus its detection metadata.

    Field names match what ``app.detection.satellite.detect_slick`` consumes so
    ``to_detection_scenario()`` is a lossless hand-off to the existing module.
    """

    acquisitionTime: str
    geometry: Dict[str, Any]
    centroid: Dict[str, float]
    sensor: Dict[str, Any] = field(default_factory=dict)
    detectionConfidence: Optional[float] = None
    detectionConfidenceNote: Optional[str] = None
    lookAlikeWarning: Optional[bool] = None
    lookAlikeAssessment: Optional[Dict[str, Any]] = None
    spillId: Optional[str] = None
    caseId: Optional[str] = None
    uiLabel: Optional[str] = None
    characteristics: Dict[str, Any] = field(default_factory=dict)
    provenance: Provenance = field(default_factory=lambda: Provenance("unknown"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "acquisitionTime": self.acquisitionTime,
            "geometry": self.geometry,
            "centroid": self.centroid,
            "sensor": self.sensor,
            "detectionConfidence": self.detectionConfidence,
            "detectionConfidenceNote": self.detectionConfidenceNote,
            "lookAlikeWarning": self.lookAlikeWarning,
            "lookAlikeAssessment": self.lookAlikeAssessment,
            "spillId": self.spillId,
            "caseId": self.caseId,
            "uiLabel": self.uiLabel,
            "characteristics": self.characteristics,
            "provenance": self.provenance.to_dict(),
        }

    def to_detection_scenario(self) -> Dict[str, Any]:
        """Return the scenario dict ``detect_slick(scenario)`` expects."""
        scenario: Dict[str, Any] = {
            "acquisitionTime": self.acquisitionTime,
            "geometry": self.geometry,
            "sensor": self.sensor,
            "synthetic": self.provenance.synthetic,
            "datasetLabel": self.provenance.datasetLabel or SYNTHETIC_LABEL,
            "provenance": self.provenance.to_dict(),
        }
        if self.uiLabel:
            scenario["uiLabel"] = self.uiLabel
        if self.spillId:
            scenario["spillId"] = self.spillId
        if self.caseId:
            scenario["caseId"] = self.caseId
        if self.detectionConfidence is not None:
            scenario["detectionConfidence"] = self.detectionConfidence
        if self.detectionConfidenceNote:
            scenario["detectionConfidenceNote"] = self.detectionConfidenceNote
        if self.lookAlikeWarning is not None:
            scenario["lookAlikeWarning"] = self.lookAlikeWarning
        if self.lookAlikeAssessment is not None:
            scenario["lookAlikeAssessment"] = self.lookAlikeAssessment
        for key in ("areaKm2", "boundingBox", "perimeterKm",
                    "approximateLengthKm", "approximateWidthKm",
                    "orientationDeg", "orientationNote"):
            if key in self.characteristics:
                scenario[key] = self.characteristics[key]
        return scenario


@dataclass
class AisReport:
    """One normalized AIS position report.

    Field names match the accepted-record keys produced by
    ``app.ais.cleaning`` so ``to_core_record()`` is a direct hand-off.
    """

    mmsi: str
    timestamp: str
    latitude: float
    longitude: float
    sogKn: Optional[float] = None
    cogDeg: Optional[float] = None
    headingDeg: Optional[float] = None
    navigationStatus: Optional[str] = None
    imo: Optional[str] = None
    vesselName: Optional[str] = None
    vesselType: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    provenance: Provenance = field(default_factory=lambda: Provenance("unknown"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mmsi": self.mmsi,
            "timestamp": self.timestamp,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "sogKn": self.sogKn,
            "cogDeg": self.cogDeg,
            "headingDeg": self.headingDeg,
            "navigationStatus": self.navigationStatus,
            "imo": self.imo,
            "vesselName": self.vesselName,
            "vesselType": self.vesselType,
            "warnings": list(self.warnings),
            "provenance": self.provenance.to_dict(),
        }

    def to_core_record(self) -> Dict[str, Any]:
        """Return the record shape ``app.ais.cleaning`` emits for accepted rows."""
        record: Dict[str, Any] = {
            "mmsi": self.mmsi,
            "timestamp": self.timestamp,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "sogKn": self.sogKn,
            "cogDeg": self.cogDeg,
            "headingDeg": self.headingDeg,
            "navigationStatus": self.navigationStatus,
            "warnings": list(self.warnings),
        }
        if self.imo is not None:
            record["imo"] = self.imo
        if self.vesselName is not None:
            record["vesselName"] = self.vesselName
        if self.vesselType is not None:
            record["vesselType"] = self.vesselType
        if self.provenance.datasetLabel:
            record["datasetLabel"] = self.provenance.datasetLabel
        record["synthetic"] = self.provenance.synthetic
        return record


@dataclass
class EnvironmentalObservation:
    """One normalized environmental sample at a point in space and time.

    Only variables the hindcast core already uses are represented: surface
    current (u/v), wind (speed and from-direction, plus u/v when supplied) and
    the windage coefficient. No new scientific quantity is introduced.
    """

    timestamp: str
    latitude: float
    longitude: float
    windSpeedMs: Optional[float] = None
    windFromDirectionDeg: Optional[float] = None
    currentSpeedMs: Optional[float] = None
    currentDirectionDeg: Optional[float] = None
    uCurrent: Optional[float] = None
    vCurrent: Optional[float] = None
    uWind: Optional[float] = None
    vWind: Optional[float] = None
    windageCoefficient: Optional[float] = None
    provenance: Provenance = field(default_factory=lambda: Provenance("unknown"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "windSpeedMs": self.windSpeedMs,
            "windFromDirectionDeg": self.windFromDirectionDeg,
            "currentSpeedMs": self.currentSpeedMs,
            "currentDirectionDeg": self.currentDirectionDeg,
            "uCurrent": self.uCurrent,
            "vCurrent": self.vCurrent,
            "uWind": self.uWind,
            "vWind": self.vWind,
            "windageCoefficient": self.windageCoefficient,
            "provenance": self.provenance.to_dict(),
        }

    def to_field_node(self) -> Dict[str, Any]:
        """Return the node shape used by ``EnvironmentalField`` grid files."""
        node: Dict[str, Any] = {"lat": self.latitude, "lon": self.longitude}
        for key in ("uCurrent", "vCurrent", "uWind", "vWind",
                    "windSpeed", "windFromDirection"):
            value = getattr(self, key, None)
            if value is not None:
                node[key] = value
        if self.windSpeedMs is not None:
            node["windSpeed"] = self.windSpeedMs
        if self.windFromDirectionDeg is not None:
            node["windFromDirection"] = self.windFromDirectionDeg
        return node


@dataclass
class NormalizedBatch:
    """A validated batch of normalized records plus its validation report."""

    contract: str
    records: List[Any] = field(default_factory=list)
    accepted: int = 0
    rejected: int = 0
    issues: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    provenance: Optional[Provenance] = None

    def to_dict(self, *, include_records: bool = False) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "contract": self.contract,
            "contractVersion": CONTRACT_VERSION,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "issues": self.issues,
            "warnings": self.warnings,
        }
        if self.provenance is not None:
            payload["provenance"] = self.provenance.to_dict()
        if include_records:
            payload["records"] = [
                r.to_dict() if hasattr(r, "to_dict") else r for r in self.records
            ]
        return payload


def _opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
