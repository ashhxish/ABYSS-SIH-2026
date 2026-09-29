"""ABYSS - REAL AIS INTEGRATION (Phase 21).

Runs a REAL historical AIS extract (NOAA / OAR / PMEL AIS point data) through
the EXISTING ABYSS AIS engine.  No AIS algorithm is re-implemented here; this
module is a thin integration boundary only:

    raw NOAA AIS CSV
        -> app.ingestion.adapters.ingest_ais_csv   (Phase 19 normalisation + validation)
        -> AisReport.to_core_record()              (documented hand-off shape)
        -> app.ais.cleaning.clean_dataframe        (Phase 3 cleaning)
        -> app.ais.trajectory.build_trajectories_from_cleaning (Phase 4 tracks + gaps)
        -> bounding-box subset selection           (spatial selection only)

CRITICAL LIMITATION
-------------------
The real Sentinel-1 scene (``00999.tif``) carries no trustworthy acquisition
timestamp, so this module NEVER claims a temporal relationship between the AIS
extract and the SAR scene.  Every result is reported with::

    "temporalMatchAvailable": false
    "temporalMatchReason": "Sentinel-1 acquisition timestamp unavailable."

No vessel is ever presented as responsible for the slick, and the scene
bounding box is used only as a SPATIAL test region.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from app.ais.cleaning import CleaningConfig, clean_dataframe
from app.ais.trajectory import (
    TrajectoryCollection,
    TrajectoryConfig,
    VesselTrajectory,
    build_trajectories_from_cleaning,
)
from app.ingestion import SYNTHETIC_LABEL, ingest_ais_csv

__all__ = [
    "REAL_AIS_SOURCE",
    "REAL_AIS_LABEL",
    "TEMPORAL_MATCH_REASON",
    "SENTINEL1_SCENE_BBOX",
    "RealAisError",
    "resolve_extract_path",
    "scene_bbox",
    "normalise_bbox",
    "point_in_bbox",
    "to_canonical_frame",
    "vessel_summary",
    "analyse_real_ais",
]

REAL_AIS_SOURCE = "NOAA/OAR/PMEL AIS"
REAL_AIS_LABEL = "REAL AIS INTEGRATION - TEMPORAL MATCH PENDING"
TEMPORAL_MATCH_REASON = "Sentinel-1 acquisition timestamp unavailable."

DEFAULT_REAL_AIS_CSV = Path.home() / "SIH" / "real_ais" / "ais_sample.csv"
REAL_AIS_CSV_ENV = "ABYSS_REAL_AIS_CSV"

#: Bounds of the real Sentinel-1 scene 00999.tif (EPSG:4326, west/south/east/north).
#: Used ONLY as a spatial test region - never as a temporal anchor.
SENTINEL1_SCENE_BBOX: Tuple[float, float, float, float] = (
    -93.5354352853,
    22.3500611723,
    -93.3514603151,
    22.5340361425,
)

#: Column order accepted by ``app.ais.cleaning.clean_dataframe``
#: (REQUIRED_COLUMNS + OPTIONAL_COLUMNS, plus the two audit columns read_ais_csv adds).
CANONICAL_AIS_COLUMNS = (
    "MMSI",
    "IMO",
    "vesselName",
    "vesselType",
    "timestamp",
    "latitude",
    "longitude",
    "SOG",
    "COG",
    "heading",
    "navigationStatus",
    "datasetLabel",
)


class RealAisError(RuntimeError):
    """Raised when the real AIS extract cannot be loaded or analysed."""


def resolve_extract_path(explicit: Optional[str] = None) -> Path:
    """Resolve the real AIS extract path: explicit > env var > documented default."""
    if explicit:
        return Path(explicit).expanduser()
    from_env = os.environ.get(REAL_AIS_CSV_ENV)
    if from_env:
        return Path(from_env).expanduser()
    return DEFAULT_REAL_AIS_CSV


def scene_bbox() -> Tuple[float, float, float, float]:
    """Return the real Sentinel-1 scene bounds (west, south, east, north)."""
    return SENTINEL1_SCENE_BBOX


def normalise_bbox(bbox: Optional[Sequence[float]]) -> Tuple[float, float, float, float]:
    """Validate a west/south/east/north box; ``None`` means the Sentinel-1 scene box."""
    if bbox is None:
        return scene_bbox()
    values = [float(value) for value in bbox]
    if len(values) != 4:
        raise RealAisError(
            "bbox must contain exactly 4 values (west, south, east, north); "
            f"got {len(values)}"
        )
    west, south, east, north = values
    if not (-180.0 <= west <= 180.0 and -180.0 <= east <= 180.0):
        raise RealAisError("bbox longitudes must lie in [-180, 180]")
    if not (-90.0 <= south <= 90.0 and -90.0 <= north <= 90.0):
        raise RealAisError("bbox latitudes must lie in [-90, 90]")
    if west > east or south > north:
        raise RealAisError("bbox must satisfy west <= east and south <= north")
    return (west, south, east, north)


def point_in_bbox(
    latitude: float,
    longitude: float,
    bbox: Tuple[float, float, float, float],
) -> bool:
    """Inclusive point-in-box test used for spatial selection only."""
    west, south, east, north = bbox
    return south <= latitude <= north and west <= longitude <= east


def _rejected_row_indices(batch: Any) -> List[int]:
    """Raw 0-based row indices that produced a Phase-19 validation ERROR."""
    indices = set()
    for issue in batch.issues:
        if issue.get("severity") == "error" and issue.get("recordIndex") is not None:
            indices.add(int(issue["recordIndex"]))
    return sorted(indices)


def to_canonical_frame(batch: Any, raw_record_count: int) -> Tuple[pd.DataFrame, List[str]]:
    """Hand off Phase-19 ``AisReport`` objects to the Phase-3 cleaning engine.

    ``AisReport.to_core_record()`` is the documented hand-off shape, so no field is
    renamed or reinterpreted here.  AIS "not available" sentinels (SOG 102.3,
    COG 360.0, heading 511) were already resolved to ``None`` by Phase-19
    validation; they arrive as blanks, which is the truthful canonical encoding
    of "the vessel reported nothing".
    """
    notes: List[str] = []
    rows: List[Dict[str, Any]] = []
    for record in batch.records:
        core = record.to_core_record()
        rows.append(
            {
                "MMSI": core.get("mmsi"),
                "IMO": core.get("imo") or "",
                "vesselName": core.get("vesselName") or "",
                "vesselType": core.get("vesselType") or "",
                "timestamp": core.get("timestamp"),
                "latitude": core.get("latitude"),
                "longitude": core.get("longitude"),
                "SOG": "" if core.get("sogKn") is None else core.get("sogKn"),
                "COG": "" if core.get("cogDeg") is None else core.get("cogDeg"),
                "heading": "" if core.get("headingDeg") is None else core.get("headingDeg"),
                "navigationStatus": core.get("navigationStatus") or "",
                "datasetLabel": core.get("datasetLabel") or REAL_AIS_SOURCE,
            }
        )
    frame = pd.DataFrame(rows, columns=list(CANONICAL_AIS_COLUMNS))

    rejected = set(_rejected_row_indices(batch))
    accepted_indices = [index for index in range(raw_record_count) if index not in rejected]
    if len(accepted_indices) == len(batch.records):
        frame["_line"] = [index + 2 for index in accepted_indices]
    else:
        frame["_line"] = list(range(2, len(batch.records) + 2))
        notes.append(
            "Raw source-line numbers could not be reconstructed for every accepted "
            "record, so sourceLine counts accepted records in the canonical hand-off "
            "frame rather than raw extract lines."
        )
    frame["_order"] = list(range(len(batch.records)))
    return frame, notes


def _parse_instant(value: Optional[str], label: str) -> Optional[pd.Timestamp]:
    """Parse an optional ISO-8601 instant; ``None``/blank means "not supplied"."""
    if value is None or str(value).strip() == "":
        return None
    stamp = pd.to_datetime(value, utc=True, errors="coerce")
    if stamp is None or pd.isna(stamp):
        raise RealAisError(f"{label} is not a recognised ISO-8601 instant: {value!r}")
    return stamp


def apply_temporal_selection(
    frame: pd.DataFrame,
    start: Optional[pd.Timestamp],
    end: Optional[pd.Timestamp],
) -> Tuple[pd.DataFrame, int]:
    """Select records inside an explicit extract window.

    This is a data-selection filter inside the AIS extract ONLY.  It is never a
    Sentinel-1 temporal match, because no Sentinel-1 acquisition time exists.
    """
    if start is None and end is None:
        return frame, 0
    stamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    mask = pd.Series(True, index=frame.index)
    if start is not None:
        mask &= stamps >= start
    if end is not None:
        mask &= stamps <= end
    removed = int((~mask).sum())
    return frame.loc[mask].copy(), removed


def _finite(value: Any) -> Optional[float]:
    """Return a JSON-safe float, or ``None`` when the value is absent or NaN."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def vessel_summary(
    trajectory: VesselTrajectory,
    matched_points: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Vessel-level track and behaviour features read from the Phase-4 engine.

    Everything here comes from the existing trajectory engine's own outputs
    (points, segments, gaps, stop/slow periods, course changes).  Nothing is
    recomputed and no responsibility score is produced.
    """
    points = list(trajectory.points)
    speeds = [value for value in (_finite(point.sogKn) for point in points) if value is not None]
    distances = [
        value for value in (_finite(segment.distanceKm) for segment in trajectory.segments)
        if value is not None
    ]
    gaps = list(trajectory.gaps)

    summary: Dict[str, Any] = {
        "mmsi": trajectory.mmsi,
        "imo": trajectory.imo,
        "vesselName": trajectory.vesselName,
        "vesselType": trajectory.vesselType,
        "datasetLabel": trajectory.datasetLabel,
        "synthetic": bool(trajectory.synthetic),
        "pointCount": len(points),
        "segmentCount": len(trajectory.segments),
        "startTimestamp": points[0].timestamp if points else None,
        "endTimestamp": points[-1].timestamp if points else None,
        "distanceKm": round(sum(distances), 3) if distances else 0.0,
        "meanSogKn": round(sum(speeds) / len(speeds), 3) if speeds else None,
        "maxSogKn": round(max(speeds), 3) if speeds else None,
        "gapCount": len(gaps),
        "longestGapSeconds": max((gap.durationSeconds for gap in gaps), default=None),
        "stopSlowPeriodCount": len(trajectory.stopSlowPeriods),
        "courseChangeCount": len(trajectory.courseChanges),
        "firstPosition": None,
        "lastPosition": None,
        "matchedPointCount": None,
        "matchedStartTimestamp": None,
        "matchedEndTimestamp": None,
        "matchedFirstPosition": None,
        "matchedLastPosition": None,
    }
    if points:
        summary["firstPosition"] = {
            "latitude": points[0].latitude,
            "longitude": points[0].longitude,
        }
        summary["lastPosition"] = {
            "latitude": points[-1].latitude,
            "longitude": points[-1].longitude,
        }
    if matched_points is not None:
        summary["matchedPointCount"] = len(matched_points)
        if matched_points:
            summary["matchedStartTimestamp"] = matched_points[0].timestamp
            summary["matchedEndTimestamp"] = matched_points[-1].timestamp
            summary["matchedFirstPosition"] = {
                "latitude": matched_points[0].latitude,
                "longitude": matched_points[0].longitude,
            }
            summary["matchedLastPosition"] = {
                "latitude": matched_points[-1].latitude,
                "longitude": matched_points[-1].longitude,
            }
    return summary


def analyse_real_ais(
    *,
    source_path: Optional[str] = None,
    bbox: Optional[Sequence[float]] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    max_records: Optional[int] = None,
    spatial_filter: bool = True,
    include_vessels: bool = True,
    cleaning_config: Optional[CleaningConfig] = None,
    trajectory_config: Optional[TrajectoryConfig] = None,
) -> Dict[str, Any]:
    """Run a real AIS extract through the existing ABYSS AIS engine.

    ``temporalMatchAvailable`` is always ``False``: the real Sentinel-1 scene
    carries no acquisition timestamp, so only spatial, trajectory, gap and
    data-quality results are produced - never a responsibility attribution.
    """
    path = resolve_extract_path(source_path)
    if not path.exists():
        raise RealAisError(f"real AIS extract not found at {path}")

    notes: List[str] = [
        f"Integration case label: {REAL_AIS_LABEL}.",
        "Real AIS data only: no synthetic CASE-001 record is loaded, merged or scored.",
        "No AIS algorithm is re-implemented: Phase-19 ingestion, Phase-3 cleaning, "
        "Phase-4 trajectories and the trajectory engine's gap detection are the "
        "existing engine.",
        "MMSI, timestamps, positions, SOG/COG/heading and vessel metadata are taken "
        "verbatim from the extract; nothing is invented.",
        f"Temporal match unavailable: {TEMPORAL_MATCH_REASON} "
        "Candidates are therefore never ranked by responsibility.",
    ]
    warnings: List[str] = []

    # ---- Stage 1: Phase 19 ingestion (normalisation + validation) ---------
    batch = ingest_ais_csv(path)
    if not batch.records:
        raise RealAisError(
            f"no AIS record in {path} passed Phase-19 contract validation "
            f"({batch.rejected} error issue(s))"
        )

    rejected_indices = _rejected_row_indices(batch)
    rejected_record_count = len(rejected_indices) if rejected_indices else batch.rejected
    raw_record_count = len(batch.records) + rejected_record_count
    unique_mmsi = sorted({record.mmsi for record in batch.records})

    if all(record.provenance.synthetic for record in batch.records):
        warnings.append(
            "The ingestion layer marked this extract synthetic, but real-AIS "
            "analysis expects real data - check the source file."
        )

    # ---- Stage 2: hand-off to Phase 3 cleaning ----------------------------
    frame, frame_notes = to_canonical_frame(batch, raw_record_count)
    notes.extend(frame_notes)

    synthetic_rows = int((frame["datasetLabel"] == SYNTHETIC_LABEL).sum())
    if synthetic_rows:
        warnings.append(
            f"{synthetic_rows} record(s) carried the synthetic demonstration label "
            "and were excluded from the real AIS analysis."
        )
        frame = frame.loc[frame["datasetLabel"] != SYNTHETIC_LABEL].copy()

    start = _parse_instant(start_time, "startTime")
    end = _parse_instant(end_time, "endTime")
    frame, dropped = apply_temporal_selection(frame, start, end)
    if dropped:
        notes.append(
            f"{dropped} record(s) outside the requested extract window were excluded "
            "(extract-internal selection only; not a Sentinel-1 temporal match)."
        )
    if max_records is not None and len(frame) > max_records:
        notes.append(
            f"maxRecords={max_records} capped the {len(frame)} selectable record(s) "
            "carried into cleaning and trajectory reconstruction."
        )
        frame = frame.head(max_records).copy()
    if frame.empty:
        raise RealAisError("no AIS record remained after the requested selection")

    source = {
        "provider": REAL_AIS_SOURCE,
        "uri": str(path),
        "synthetic": False,
        "syntheticInferredFromData": False,
        "datasetLabels": sorted({str(value) for value in frame["datasetLabel"].unique() if value}),
    }
    cleaning = clean_dataframe(frame, cleaning_config or CleaningConfig(), source=source)

    # ---- Stage 3: Phase 4 trajectory reconstruction + gap detection -------
    collection: TrajectoryCollection = build_trajectories_from_cleaning(
        cleaning, trajectory_config or TrajectoryConfig()
    )


    # ---- Stage 4: spatial selection (spatial only, never temporal) --------
    applied_bbox: Optional[Tuple[float, float, float, float]] = (
        normalise_bbox(bbox) if spatial_filter else None
    )
    matched_trajectories: List[VesselTrajectory] = []
    matched_point_count = 0
    vessels: List[Dict[str, Any]] = []
    for trajectory in collection.trajectories:
        if applied_bbox is None:
            matched = list(trajectory.points)
        else:
            matched = [
                point
                for point in trajectory.points
                if point_in_bbox(point.latitude, point.longitude, applied_bbox)
            ]
            if not matched:
                continue
        matched_trajectories.append(trajectory)
        matched_point_count += len(matched)
        if include_vessels:
            vessels.append(
                vessel_summary(trajectory, matched if applied_bbox is not None else None)
            )

    gap_count = sum(len(trajectory.gaps) for trajectory in collection.trajectories)
    issue_sample = batch.issues[:20]
    warning_sample = list(batch.warnings[:50])
    if len(batch.warnings) > len(warning_sample):
        notes.append(
            f"Only the first {len(warning_sample)} of {len(batch.warnings)} validation "
            "warnings are listed; warningCount reports the full total."
        )
    if not matched_trajectories:
        warnings.append(
            "No real AIS position falls inside the spatial selection region; zero "
            "matches is reported honestly and no record was fabricated."
        )

    analysis: Dict[str, Any] = {
        "caseLabel": REAL_AIS_LABEL,
        "ingestion": {
            "contract": batch.contract,
            "accepted": batch.accepted,
            "rejectedErrorIssues": batch.rejected,
            "rejectedRecordCount": rejected_record_count,
            "warningCount": len(batch.warnings),
            "rejectedRowIndices": rejected_indices,
            "issues": issue_sample,
            "issuesTruncated": max(0, len(batch.issues) - len(issue_sample)),
            "warningsSample": warning_sample,
        },
        "cleaning": {
            "recordCount": len(cleaning.records),
            "vesselCount": len(cleaning.vessels),
            "rejectedCount": len(cleaning.rejected),
            "removedValueCount": len(cleaning.removed_values),
            "warningCount": len(cleaning.warnings),
            "statistics": cleaning.statistics,
            "source": cleaning.source,
        },
        "trajectories": {
            "trajectoryCount": len(collection.trajectories),
            "skippedRecordCount": len(collection.skippedRecords),
            "warningCount": len(collection.warnings),
            "statistics": collection.statistics,
        },
        "spatial": {
            "spatialFilterApplied": applied_bbox is not None,
            "bbox": list(applied_bbox) if applied_bbox is not None else None,
            "matchedTrajectoryCount": len(matched_trajectories),
            "matchedPointCount": matched_point_count,
            "matchedGapCount": sum(len(item.gaps) for item in matched_trajectories),
            "note": (
                "Spatial selection only: the real Sentinel-1 scene has no acquisition "
                "timestamp, so no temporal correlation and no responsibility "
                "attribution is made."
            ),
        },
        "dataQuality": {
            "uniqueMmsiCount": len(unique_mmsi),
            "syntheticRecordCount": synthetic_rows,
            "recordsWithReportedSog": int(frame["SOG"].astype(str).str.strip().ne("").sum()),
            "recordsWithVesselName": int(frame["vesselName"].astype(str).str.strip().ne("").sum()),
            "recordsWithImo": int(frame["IMO"].astype(str).str.strip().ne("").sum()),
        },
    }

    return {
        "label": REAL_AIS_LABEL,
        "realAis": True,
        "source": source,
        "temporalMatchAvailable": False,
        "temporalMatchReason": TEMPORAL_MATCH_REASON,
        "rawRecordCount": raw_record_count,
        "acceptedRecordCount": len(batch.records),
        "rejectedRecordCount": rejected_record_count,
        "warningCount": len(batch.warnings),
        "uniqueMmsiCount": len(unique_mmsi),
        "filteredRecordCount": matched_point_count,
        "vesselCount": len(matched_trajectories),
        "trajectoryCount": len(collection.trajectories),
        "gapCount": gap_count,
        "spatialFilterApplied": applied_bbox is not None,
        "spatialBBox": list(applied_bbox) if applied_bbox is not None else None,
        "spatialMatchCount": matched_point_count,
        "vessels": vessels,
        "uniqueMmsi": unique_mmsi,
        "analysis": analysis,
        "warnings": warnings + warning_sample,
        "notes": notes,
    }
