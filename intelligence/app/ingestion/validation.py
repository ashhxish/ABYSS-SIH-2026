"""ABYSS - Phase 19 input validation.

Validates raw records against the normalized contracts before they reach the
forensic core. Two outcomes are possible and both are explicit:

  * **error** - the record cannot be normalized; it is rejected and the reason,
    the offending field and the raw value are kept in the report.
  * **warning** - the record is usable but something optional was missing,
    out of range, or inconsistent; the value is dropped and the report says so.

Validation never mutates its input, never invents a value, and never silently
drops a record: every rejection is reproducible from the returned report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.timeutils import iso_z, parse_iso_z

from .contracts import (
    AisReport,
    EnvironmentalObservation,
    NormalizedBatch,
    Provenance,
    SatelliteObservation,
    _MMSI_RE,
)

__all__ = [
    "ValidationIssue",
    "ValidationReport",
    "validate_satellite_observation",
    "validate_ais_report",
    "validate_environmental_observation",
    "normalize_batch",
]

ERROR = "error"
WARNING = "warning"

# AIS "not available" sentinels already honoured by app.ais.cleaning. They are
# reported here as warnings so the boundary and the core agree on one meaning.
_SOG_SENTINEL = 102.3
_COG_SENTINEL = 360.0
_HEADING_SENTINEL = 511


@dataclass(frozen=True)
class ValidationIssue:
    """One reason a record was rejected or flagged."""

    severity: str
    code: str
    message: str
    field: Optional[str] = None
    recordIndex: Optional[int] = None
    recordId: Optional[str] = None
    value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "recordIndex": self.recordIndex,
            "recordId": self.recordId,
            "value": self.value,
        }


@dataclass
class ValidationReport:
    """The outcome of validating one batch of records."""

    records: List[Any] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def accepted(self) -> int:
        return len(self.records)

    @property
    def rejected(self) -> int:
        return sum(1 for i in self.issues if i.severity == ERROR)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "issues": [i.to_dict() for i in self.issues],
            "warnings": list(self.warnings),
        }


def _issue(severity: str, code: str, message: str, *, field_name: Optional[str] = None,
           record_index: Optional[int] = None, record_id: Optional[str] = None,
           value: Any = None) -> ValidationIssue:
    return ValidationIssue(severity, code, message, field_name, record_index,
                           record_id, value)


# ---------------------------------------------------------------------------
# Scalar helpers - shared by the three record validators
# ---------------------------------------------------------------------------

# WGS84 validity ranges used everywhere in the ABYSS core.
LAT_RANGE = (-90.0, 90.0)
LON_RANGE = (-180.0, 180.0)
SOG_RANGE = (0.0, 102.2)   # 102.3 is the AIS "not available" sentinel
COG_RANGE = (0.0, 359.9)   # 360.0 is the AIS "not available" sentinel
HEADING_RANGE = (0.0, 511.0)  # 511 is the AIS "not available" sentinel


def _as_float(value: Any) -> Tuple[Optional[float], Optional[str]]:
    """Return ``(number, None)`` or ``(None, reason)``. Booleans are not numbers."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    if isinstance(value, bool):
        return None, f"expected a number, got boolean {value!r}"
    try:
        return float(value), None
    except (TypeError, ValueError):
        return None, f"expected a number, got {value!r}"


def _numeric(name: str, value: Any, *, field_name: str,
             record_index: Optional[int] = None,
             record_id: Optional[str] = None,
             required: bool = False,
             rng: Optional[Tuple[float, float]] = None,
             issues: List[ValidationIssue]) -> Optional[float]:
    """Parse one numeric field. Structural failure -> error; out of range -> warning."""
    number, reason = _as_float(value)
    if reason is not None:
        issues.append(_issue(ERROR, "not_numeric", f"{name}: {reason}",
                             field_name=field_name, record_index=record_index,
                             record_id=record_id, value=value))
        return None
    if number is None:
        if required:
            issues.append(_issue(ERROR, "missing_required_field",
                                 f"{name} is required and was not supplied",
                                 field_name=field_name, record_index=record_index,
                                 record_id=record_id))
        return None
    if rng is not None and not (rng[0] <= number <= rng[1]):
        issues.append(_issue(
            WARNING, "out_of_range",
            f"{name} {number} is outside [{rng[0]}, {rng[1]}]; value dropped",
            field_name=field_name, record_index=record_index,
            record_id=record_id, value=number))
        return None
    return number


def _timestamp(value: Any, *, field_name: str = "timestamp",
               record_index: Optional[int] = None,
               record_id: Optional[str] = None,
               issues: List[ValidationIssue]) -> Optional[str]:
    """Normalize a timestamp to the demo's canonical `...Z` UTC form.

    The value is echoed back exactly as parsed - normalization to UTC is the
    only change, and unparseable input is an error rather than a dropped record.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        issues.append(_issue(ERROR, "missing_required_field",
                             "timestamp is required and was not supplied",
                             field_name=field_name, record_index=record_index,
                             record_id=record_id, value=value))
        return None
    try:
        return iso_z(parse_iso_z(value))
    except (ValueError, TypeError) as exc:
        issues.append(_issue(ERROR, "malformed_timestamp", str(exc),
                             field_name=field_name, record_index=record_index,
                             record_id=record_id, value=value))
        return None


def _sentinel(name: str, value: Optional[float], sentinel: float, *,
              field_name: str, record_index: Optional[int],
              record_id: Optional[str], issues: List[ValidationIssue]) -> Optional[float]:
    """Drop an AIS 'not available' sentinel with an explicit warning."""
    if value is not None and value == sentinel:
        issues.append(_issue(
            WARNING, "not_available_sentinel",
            f"{name} {sentinel} is the AIS 'not available' sentinel; treated as missing",
            field_name=field_name, record_index=record_index,
            record_id=record_id, value=value))
        return None
    return value


def _opt_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _mmsi(value: Any, *, record_index: Optional[int],
          record_id: Optional[str], issues: List[ValidationIssue]) -> Optional[str]:
    """Return the 9-digit MMSI as text, or None with an error recorded."""
    if value is None or (isinstance(value, str) and not value.strip()):
        issues.append(_issue(ERROR, "missing_required_field", "mmsi is required",
                             field_name="mmsi", record_index=record_index,
                             record_id=record_id, value=value))
        return None
    text = str(value).strip()
    if not _MMSI_RE.match(text):
        issues.append(_issue(ERROR, "invalid_mmsi",
                             f"mmsi {text!r} is not 9 digits",
                             field_name="mmsi", record_index=record_index,
                             record_id=record_id, value=value))
        return None
    return text


def _vessel_type(value: Any) -> Optional[str]:
    """Normalise an AIS ship-type code to its canonical integer text form.

    AIS ship-and-cargo-type is a whole-number code (0-99). Some real-world
    extractors - NOAA PMEL ERDDAP among them - serialise it as a float, so the
    same tanker arrives as ``70`` from one source and ``"70.0"`` from another.
    ``app.ais.trajectory`` casts this field with ``int()``, so a float-formatted
    code would abort trajectory reconstruction on an otherwise valid record.

    The value is therefore coerced to the nearest whole code when it is
    numerically integral, and passed through untouched when it is not numeric
    at all (so genuinely unrecognised codes still reach the existing
    ``unknown_vessel_type`` warning path rather than being silently dropped).
    """
    text = _opt_text(value)
    if text is None:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return text
    if number.is_integer():
        return str(int(number))
    return text


# ---------------------------------------------------------------------------
# Record Validators
# ---------------------------------------------------------------------------

def validate_satellite_observation(
    raw: Dict[str, Any],
    record_index: Optional[int] = None,
) -> Tuple[Optional[SatelliteObservation], List[ValidationIssue]]:
    """Validate a raw satellite observation payload against SatelliteObservation contract."""
    issues: List[ValidationIssue] = []
    if not isinstance(raw, dict):
        issues.append(_issue(ERROR, "invalid_record_type", f"expected dict, got {type(raw).__name__}",
                             record_index=record_index))
        return None, issues

    record_id = _opt_text(raw.get("spillId") or raw.get("caseId"))

    acq_time = _timestamp(raw.get("acquisitionTime"), field_name="acquisitionTime",
                          record_index=record_index, record_id=record_id, issues=issues)

    geom = raw.get("geometry")
    if geom is None or not isinstance(geom, dict):
        issues.append(_issue(ERROR, "missing_required_field", "geometry is required and must be a dict",
                             field_name="geometry", record_index=record_index, record_id=record_id))
    elif "coordinates" not in geom:
        issues.append(_issue(ERROR, "invalid_geometry", "geometry must contain 'coordinates'",
                             field_name="geometry", record_index=record_index, record_id=record_id))

    centroid = raw.get("centroid")
    if centroid is None or not isinstance(centroid, dict):
        issues.append(_issue(ERROR, "missing_required_field", "centroid is required and must be a dict with lat/lon",
                             field_name="centroid", record_index=record_index, record_id=record_id))
    else:
        c_lat = _numeric("centroid.lat", centroid.get("lat"), field_name="centroid.lat",
                         record_index=record_index, record_id=record_id, required=True, rng=LAT_RANGE, issues=issues)
        c_lon = _numeric("centroid.lon", centroid.get("lon"), field_name="centroid.lon",
                         record_index=record_index, record_id=record_id, required=True, rng=LON_RANGE, issues=issues)
        if c_lat is not None and c_lon is not None:
            centroid = {"lat": c_lat, "lon": c_lon}

    if any(issue.severity == ERROR for issue in issues):
        return None, issues

    sensor = raw.get("sensor")
    if sensor is None or not isinstance(sensor, dict):
        sensor = {}

    conf = _numeric("detectionConfidence", raw.get("detectionConfidence"),
                    field_name="detectionConfidence", record_index=record_index,
                    record_id=record_id, rng=(0.0, 1.0), issues=issues)

    prov_data = raw.get("provenance")
    if isinstance(prov_data, dict):
        prov = Provenance.from_dict(prov_data, sourceType="satellite")
    elif isinstance(prov_data, Provenance):
        prov = prov_data
    else:
        prov = Provenance(
            sourceType="satellite",
            sourceName=_opt_text(sensor.get("name")),
            synthetic=bool(raw.get("synthetic", False)),
            datasetLabel=_opt_text(raw.get("datasetLabel")),
        )

    characteristics: Dict[str, Any] = {}
    for key in ("areaKm2", "boundingBox", "perimeterKm",
                "approximateLengthKm", "approximateWidthKm",
                "orientationDeg", "orientationNote"):
        if key in raw:
            characteristics[key] = raw[key]

    obs = SatelliteObservation(
        acquisitionTime=acq_time,  # type: ignore[arg-type]
        geometry=geom,             # type: ignore[arg-type]
        centroid=centroid,         # type: ignore[arg-type]
        sensor=sensor,
        detectionConfidence=conf,
        detectionConfidenceNote=_opt_text(raw.get("detectionConfidenceNote")),
        lookAlikeWarning=bool(raw["lookAlikeWarning"]) if "lookAlikeWarning" in raw and raw["lookAlikeWarning"] is not None else None,
        lookAlikeAssessment=raw.get("lookAlikeAssessment") if isinstance(raw.get("lookAlikeAssessment"), dict) else None,
        spillId=_opt_text(raw.get("spillId")),
        caseId=_opt_text(raw.get("caseId")),
        uiLabel=_opt_text(raw.get("uiLabel")),
        characteristics=characteristics,
        provenance=prov,
    )
    return obs, issues


def validate_ais_report(
    raw: Dict[str, Any],
    record_index: Optional[int] = None,
) -> Tuple[Optional[AisReport], List[ValidationIssue]]:
    """Validate a raw AIS report row/record against AisReport contract."""
    issues: List[ValidationIssue] = []
    if not isinstance(raw, dict):
        issues.append(_issue(ERROR, "invalid_record_type", f"expected dict, got {type(raw).__name__}",
                             record_index=record_index))
        return None, issues

    raw_mmsi = raw.get("mmsi", raw.get("MMSI"))
    mmsi = _mmsi(raw_mmsi, record_index=record_index, record_id=str(raw_mmsi) if raw_mmsi else None, issues=issues)

    ts_val = raw.get("timestamp", raw.get("TIMESTAMP", raw.get("time", raw.get("BaseDateTime", raw.get("BASEDATETIME")))))
    ts = _timestamp(ts_val, field_name="timestamp", record_index=record_index, record_id=mmsi, issues=issues)

    lat_val = raw.get("latitude", raw.get("LATITUDE", raw.get("lat", raw.get("Lat", raw.get("LAT")))))
    lat = _numeric("latitude", lat_val, field_name="latitude", record_index=record_index,
                   record_id=mmsi, required=True, rng=LAT_RANGE, issues=issues)

    lon_val = raw.get("longitude", raw.get("LONGITUDE", raw.get("lon", raw.get("Lon", raw.get("LON")))))
    lon = _numeric("longitude", lon_val, field_name="longitude", record_index=record_index,
                   record_id=mmsi, required=True, rng=LON_RANGE, issues=issues)

    if any(issue.severity == ERROR for issue in issues):
        return None, issues

    sog_val = raw.get("sogKn", raw.get("SOG", raw.get("sog")))
    sog = _numeric("sogKn", sog_val, field_name="sogKn", record_index=record_index,
                   record_id=mmsi, rng=SOG_RANGE, issues=issues)
    sog = _sentinel("sogKn", sog, _SOG_SENTINEL, field_name="sogKn",
                    record_index=record_index, record_id=mmsi, issues=issues)

    cog_val = raw.get("cogDeg", raw.get("COG", raw.get("cog")))
    cog = _numeric("cogDeg", cog_val, field_name="cogDeg", record_index=record_index,
                   record_id=mmsi, rng=COG_RANGE, issues=issues)
    cog = _sentinel("cogDeg", cog, _COG_SENTINEL, field_name="cogDeg",
                    record_index=record_index, record_id=mmsi, issues=issues)

    hdg_val = raw.get("headingDeg", raw.get("heading", raw.get("HEADING", raw.get("Heading"))))
    hdg = _numeric("headingDeg", hdg_val, field_name="headingDeg", record_index=record_index,
                   record_id=mmsi, rng=HEADING_RANGE, issues=issues)
    hdg = _sentinel("headingDeg", hdg, _HEADING_SENTINEL, field_name="headingDeg",
                    record_index=record_index, record_id=mmsi, issues=issues)

    nav_status = _opt_text(raw.get("navigationStatus", raw.get("NAV_STATUS", raw.get("Status", raw.get("status")))))
    imo = _opt_text(raw.get("imo", raw.get("IMO")))
    vessel_name = _opt_text(raw.get("vesselName", raw.get("vessel_name", raw.get("VESSEL_NAME", raw.get("VesselName")))))
    vessel_type = _vessel_type(raw.get("vesselType", raw.get("vessel_type",
                                 raw.get("VESSEL_TYPE", raw.get("VesselType")))))

    warnings = [i.message for i in issues if i.severity == WARNING]

    prov_data = raw.get("provenance")
    if isinstance(prov_data, dict):
        prov = Provenance.from_dict(prov_data, sourceType="ais")
    elif isinstance(prov_data, Provenance):
        prov = prov_data
    else:
        prov = Provenance(
            sourceType="ais",
            sourceName="AIS",
            synthetic=bool(raw.get("synthetic", False) or "Synthetic" in str(raw.get("datasetLabel", ""))),
            datasetLabel=_opt_text(raw.get("datasetLabel")),
        )

    report = AisReport(
        mmsi=mmsi,  # type: ignore[arg-type]
        timestamp=ts,  # type: ignore[arg-type]
        latitude=lat,  # type: ignore[arg-type]
        longitude=lon,  # type: ignore[arg-type]
        sogKn=sog,
        cogDeg=cog,
        headingDeg=hdg,
        navigationStatus=nav_status,
        imo=imo,
        vesselName=vessel_name,
        vesselType=vessel_type,
        warnings=warnings,
        provenance=prov,
    )
    return report, issues


def validate_environmental_observation(
    raw: Dict[str, Any],
    record_index: Optional[int] = None,
) -> Tuple[Optional[EnvironmentalObservation], List[ValidationIssue]]:
    """Validate a single environmental sample point against EnvironmentalObservation contract."""
    issues: List[ValidationIssue] = []
    if not isinstance(raw, dict):
        issues.append(_issue(ERROR, "invalid_record_type", f"expected dict, got {type(raw).__name__}",
                             record_index=record_index))
        return None, issues

    ts_val = raw.get("timestamp", raw.get("time"))
    ts = _timestamp(ts_val, field_name="timestamp", record_index=record_index, issues=issues)

    lat_val = raw.get("latitude", raw.get("lat"))
    lat = _numeric("latitude", lat_val, field_name="latitude", record_index=record_index,
                   required=True, rng=LAT_RANGE, issues=issues)

    lon_val = raw.get("longitude", raw.get("lon"))
    lon = _numeric("longitude", lon_val, field_name="longitude", record_index=record_index,
                   required=True, rng=LON_RANGE, issues=issues)

    if any(issue.severity == ERROR for issue in issues):
        return None, issues

    wind_speed = _numeric("windSpeedMs", raw.get("windSpeedMs", raw.get("windSpeed")),
                          field_name="windSpeedMs", record_index=record_index,
                          rng=(0.0, 150.0), issues=issues)
    wind_from = _numeric("windFromDirectionDeg", raw.get("windFromDirectionDeg", raw.get("windDirection", raw.get("windFromDirection"))),
                         field_name="windFromDirectionDeg", record_index=record_index,
                         rng=(0.0, 360.0), issues=issues)
    cur_speed = _numeric("currentSpeedMs", raw.get("currentSpeedMs", raw.get("currentSpeed")),
                         field_name="currentSpeedMs", record_index=record_index,
                         rng=(0.0, 30.0), issues=issues)
    cur_dir = _numeric("currentDirectionDeg", raw.get("currentDirectionDeg", raw.get("currentDirection")),
                       field_name="currentDirectionDeg", record_index=record_index,
                       rng=(0.0, 360.0), issues=issues)
    u_cur = _numeric("uCurrent", raw.get("uCurrent"), field_name="uCurrent",
                     record_index=record_index, rng=(-30.0, 30.0), issues=issues)
    v_cur = _numeric("vCurrent", raw.get("vCurrent"), field_name="vCurrent",
                     record_index=record_index, rng=(-30.0, 30.0), issues=issues)
    u_w = _numeric("uWind", raw.get("uWind"), field_name="uWind",
                   record_index=record_index, rng=(-150.0, 150.0), issues=issues)
    v_w = _numeric("vWind", raw.get("vWind"), field_name="vWind",
                   record_index=record_index, rng=(-150.0, 150.0), issues=issues)
    windage = _numeric("windageCoefficient", raw.get("windageCoefficient"),
                       field_name="windageCoefficient", record_index=record_index,
                       rng=(0.0, 1.0), issues=issues)

    prov_data = raw.get("provenance")
    if isinstance(prov_data, dict):
        prov = Provenance.from_dict(prov_data, sourceType="environmental")
    elif isinstance(prov_data, Provenance):
        prov = prov_data
    else:
        prov = Provenance(
            sourceType="environmental",
            sourceName=_opt_text(raw.get("provider")),
            synthetic=bool(raw.get("synthetic", False)),
            datasetLabel=_opt_text(raw.get("datasetLabel")),
        )

    obs = EnvironmentalObservation(
        timestamp=ts,  # type: ignore[arg-type]
        latitude=lat,  # type: ignore[arg-type]
        longitude=lon,  # type: ignore[arg-type]
        windSpeedMs=wind_speed,
        windFromDirectionDeg=wind_from,
        currentSpeedMs=cur_speed,
        currentDirectionDeg=cur_dir,
        uCurrent=u_cur,
        vCurrent=v_cur,
        uWind=u_w,
        vWind=v_w,
        windageCoefficient=windage,
        provenance=prov,
    )
    return obs, issues


def normalize_batch(
    contract: str,
    raw_records: List[Dict[str, Any]],
    *,
    provenance: Optional[Provenance] = None,
) -> NormalizedBatch:
    """Validate and normalize a collection of raw records into a NormalizedBatch.

    contract must be one of: "satellite", "ais", "environmental".
    """
    validators = {
        "satellite": validate_satellite_observation,
        "ais": validate_ais_report,
        "environmental": validate_environmental_observation,
    }
    if contract not in validators:
        raise ValueError(f"Unknown contract {contract!r}; expected one of {list(validators.keys())}")

    validator = validators[contract]
    accepted_records: List[Any] = []
    all_issues: List[ValidationIssue] = []
    warnings: List[str] = []

    for index, raw in enumerate(raw_records):
        record, issues = validator(raw, record_index=index)
        all_issues.extend(issues)
        if record is not None:
            accepted_records.append(record)
        for issue in issues:
            if issue.severity == WARNING:
                warnings.append(f"[{issue.code}] record {index}: {issue.message}")

    batch_issues = [i.to_dict() for i in all_issues]
    rejected_count = sum(1 for i in all_issues if i.severity == ERROR)

    return NormalizedBatch(
        contract=contract,
        records=accepted_records,
        accepted=len(accepted_records),
        rejected=rejected_count,
        issues=batch_issues,
        warnings=warnings,
        provenance=provenance,
    )


