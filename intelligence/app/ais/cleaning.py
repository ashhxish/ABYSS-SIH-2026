"""ABYSS - AIS ingestion and cleaning (Phase 3).

PURPOSE
    Turn a raw AIS CSV extract into normalised, validated, time-ordered records that
    later phases can trust - while keeping a complete audit trail of every row that
    was rejected and every value that was removed.

HARD RULES IMPLEMENTED HERE
    1. NOTHING IS DROPPED SILENTLY. Every rejected row is returned with its source
       file line number, the raw values, a category and a human-readable reason;
       every removed value is returned the same way. Cleaning statistics state counts
       per category, per vessel and overall.
    2. Cleaning is deterministic: identical input gives identical output, including
       audit ordering.
    3. Thresholds are CONFIGURATION, not constants of nature (see CleaningConfig):
       the impossible-speed threshold is a prototype value that must be tuned for a
       real dataset and is reported in the output.
    4. Suspicious records are preserved for inspection, not deleted: an invalid row
       lands in `rejected` with its original values intact, and a valid row that
       contained one impossible value keeps its position with that value set to null
       plus a warning.
    5. Synthetic demonstration data stays labelled as such (see `synthetic`).

WHAT THIS MODULE DELIBERATELY DOES NOT DO (later phases own these)
    No trajectory construction or gap detection (Phases 4, 9), no spatial, temporal
    or trajectory filtering (Phases 5-7), no behaviour analysis (Phase 8), no
    evidence scoring (Phase 10). It never concludes anything about a vessel: it only
    records what the data does and does not contain.

REJECTION PRECEDENCE
    A row is rejected for the FIRST problem found, in this order:
        1. missing_required_field          blank timestamp / latitude / longitude
        2. malformed_timestamp             not a recognised ISO-8601 instant
        3. invalid_coordinate              non-numeric, out of range, or (0, 0)
        4. missing_vessel_identifier       blank MMSI
        5. invalid_vessel_identifier       MMSI not 9 digits
        6. duplicate_record                identical to an earlier row
        7. impossible_speed                unreachable given the previous record
    Each audit entry carries the primary category plus the raw values, so no
    information about the row is lost. Counts are therefore disjoint and sum to
    `rowsRejected`.

CLI
    Run from the intelligence/ directory so that `app` is importable:

        cd intelligence
        ../.venv/bin/python -m app.ais.cleaning                  # clean the demo CASE-001 extract
        ../.venv/bin/python -m app.ais.cleaning --input raw.csv --json /tmp/cleaning.json
        ../.venv/bin/python -m app.ais.cleaning --out-cleaned /tmp/clean.csv --max-speed-kn 45

    (Running the file directly also works: python3 intelligence/app/ais/cleaning.py)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

if __package__ in (None, ""):  # executed directly as a script
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app import config as app_config
    from app.geo import KNOTS_TO_KMH, haversine_km, implied_speed_kn, validate_coordinate
else:
    from app import config as app_config
    from app.geo import KNOTS_TO_KMH, haversine_km, implied_speed_kn, validate_coordinate

MODULE_VERSION = "1.0.0"

REQUIRED_COLUMNS = ("MMSI", "timestamp", "latitude", "longitude")
OPTIONAL_COLUMNS = (
    "IMO", "vesselName", "vesselType", "SOG", "COG", "heading", "navigationStatus", "datasetLabel",
)

# Standard AIS "not available" sentinels (widely implemented ITU-R M.1371 convention).
# Mapping them to null is correct AIS semantics: they mean "not reported", not zero
# and not north. They are configurable because a dataset that does not use the
# convention should be able to disable the behaviour - and because strict conformance
# needs verification against the specific revision of the standard in force.
AIS_NOT_AVAILABLE_SOG_KN = 102.3
AIS_NOT_AVAILABLE_COG_DEG = 360.0
AIS_NOT_AVAILABLE_HEADING_DEG = 511

# ---------------------------------------------------------------------------
# Rejection categories: the row is not usable as evidence
# ---------------------------------------------------------------------------
REJECT_MISSING_REQUIRED_FIELD = "missing_required_field"
REJECT_MALFORMED_TIMESTAMP = "malformed_timestamp"
REJECT_INVALID_COORDINATE = "invalid_coordinate"
REJECT_MISSING_IDENTIFIER = "missing_vessel_identifier"
REJECT_INVALID_IDENTIFIER = "invalid_vessel_identifier"
REJECT_DUPLICATE = "duplicate_record"
REJECT_IMPOSSIBLE_SPEED = "impossible_speed"
REJECTION_CATEGORIES = (
    REJECT_MISSING_REQUIRED_FIELD, REJECT_MALFORMED_TIMESTAMP, REJECT_INVALID_COORDINATE,
    REJECT_MISSING_IDENTIFIER, REJECT_INVALID_IDENTIFIER, REJECT_DUPLICATE, REJECT_IMPOSSIBLE_SPEED,
)

# ---------------------------------------------------------------------------
# Removed-value categories: the row is kept, one field is set to null
# ---------------------------------------------------------------------------
REMOVE_INVALID_SPEED = "invalid_speed_value"
REMOVE_INVALID_COURSE = "invalid_course_value"
REMOVE_INVALID_HEADING = "invalid_heading_value"
REMOVE_INVALID_NAVIGATION_STATUS = "invalid_navigation_status_value"
REMOVE_NOT_AVAILABLE = "not_available_sentinel"
REMOVED_VALUE_CATEGORIES = (
    REMOVE_INVALID_SPEED, REMOVE_INVALID_COURSE, REMOVE_INVALID_HEADING,
    REMOVE_INVALID_NAVIGATION_STATUS, REMOVE_NOT_AVAILABLE,
)

# ---------------------------------------------------------------------------
# Row-level warnings: the row is kept and remains usable
# ---------------------------------------------------------------------------
WARN_MISSING_OPTIONAL = "missing_optional_field"
WARN_CONFLICTING_TIMESTAMP = "conflicting_position_same_timestamp"
WARN_INVALID_IMO = "invalid_imo"
WARN_UNKNOWN_VESSEL_TYPE = "unknown_vessel_type"
WARN_MISSING_NAME = "missing_vessel_name"
WARN_ASSUMED_UTC = "timestamp_assumed_utc"
WARNING_CATEGORIES = (
    WARN_MISSING_OPTIONAL, WARN_CONFLICTING_TIMESTAMP, WARN_INVALID_IMO,
    WARN_UNKNOWN_VESSEL_TYPE, WARN_MISSING_NAME, WARN_ASSUMED_UTC,
)

SYNTHETIC_LABEL = "Synthetic Demonstration Dataset"
SYNTHETIC_UI_WARNING = "AIS: Synthetic Demonstration Dataset"

_RE_ISO_Z = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
_RE_ISO_NAIVE_T = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"
_RE_ISO_NAIVE_SPACE = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
_RE_ISO_OFFSET = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})$"
_RE_MMSI = r"^\d{9}$"
_RE_IMO = r"^\d{7}$"

_RE_MMSI_PATTERN = re.compile(_RE_MMSI)
_RE_IMO_PATTERN = re.compile(_RE_IMO)


class AisIngestionError(RuntimeError):
    """Raised when the source cannot be ingested at all (missing file, bad schema)."""


@dataclass(frozen=True)
class CleaningConfig:
    """Configurable cleaning thresholds.

    `max_plausible_speed_kn` is a PROTOTYPE value, not a physical constant: 60 kn is
    above every commercial vessel and below the artefacts that a receiver or a
    scenario injects. It must be tuned per dataset and is reported in the output.
    """

    max_plausible_speed_kn: float = 60.0
    null_island_tolerance_deg: float = 1e-6
    treat_not_available_sentinels: bool = True
    assume_naive_timestamp_is_utc: bool = True
    max_audit_records: int = 1000

    def __post_init__(self) -> None:
        if not (0.0 < self.max_plausible_speed_kn <= 200.0):
            raise ValueError(
                f"max_plausible_speed_kn must be in (0, 200], got {self.max_plausible_speed_kn}"
            )
        if self.null_island_tolerance_deg < 0.0:
            raise ValueError("null_island_tolerance_deg must be >= 0")
        if self.max_audit_records < 1:
            raise ValueError("max_audit_records must be >= 1")

    def describe(self) -> Dict[str, Any]:
        return {
            "maxPlausibleSpeedKn": self.max_plausible_speed_kn,
            "nullIslandToleranceDeg": self.null_island_tolerance_deg,
            "treatNotAvailableSentinels": self.treat_not_available_sentinels,
            "assumeNaiveTimestampIsUtc": self.assume_naive_timestamp_is_utc,
            "maxAuditRecords": self.max_audit_records,
        }


@dataclass
class CleaningResult:
    """Cleaned records plus the complete audit trail."""

    records: List[Dict[str, Any]] = field(default_factory=list)
    vessels: List[Dict[str, Any]] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    removed_values: List[Dict[str, Any]] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    source: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)

    @property
    def data_source(self) -> str:
        return self.source.get("provider", "DemoAISProvider")

    @property
    def synthetic(self) -> bool:
        return bool(self.source.get("synthetic"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module": "ais.cleaning",
            "moduleVersion": MODULE_VERSION,
            "dataSource": self.data_source,
            "synthetic": self.synthetic,
            "datasetLabels": self.source.get("datasetLabels", []),
            "source": self.source,
            "config": self.config,
            "counts": self.statistics.get("counts", {}),
            "statistics": self.statistics,
            "warnings": self.warnings,
            "notes": self.notes,
            "vessels": self.vessels,
            "records": self.records,
            "rejected": self.rejected,
            "removedValues": self.removed_values,
        }


# ---------------------------------------------------------------------------
# Ingestion and parsing helpers
# ---------------------------------------------------------------------------
def read_ais_csv(path: Path) -> pd.DataFrame:
    """Read a raw AIS CSV as strings, preserving blanks and adding a source line number."""
    path = Path(path)
    if not path.exists():
        raise AisIngestionError(f"AIS source file not found: {path}")
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8")
    except Exception as exc:  # pandas raises several different exception types
        raise AisIngestionError(f"could not read AIS CSV {path}: {exc}") from exc
    if len(df) == 0:
        raise AisIngestionError(f"AIS source file has no data rows: {path}")
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise AisIngestionError(
            "AIS source is missing required column(s): " + ", ".join(missing)
            + " | columns found: " + ", ".join(str(c) for c in df.columns)
        )
    for column in OPTIONAL_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    # 1-based line number in the source file (the header is line 1), so every audit
    # entry points at the exact row an investigator can open in a text editor.
    df["_line"] = np.arange(2, len(df) + 2, dtype=np.int64)
    df["_order"] = np.arange(len(df), dtype=np.int64)
    return df


def _parse_timestamps(raw: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Parse timestamps to UTC. Returns (parsed, assumed_utc, malformed).

    Blank values are reported as malformed here and reclassified by the caller as
    `missing_required_field`; that keeps the parsing logic in one place.
    """
    parsed = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns, UTC]")
    assumed = pd.Series(False, index=raw.index, dtype=bool)

    mask = raw.str.match(_RE_ISO_Z).fillna(False)
    if mask.any():
        parsed.loc[mask] = pd.to_datetime(raw[mask], format="%Y-%m-%dT%H:%M:%SZ", utc=True, errors="coerce")

    mask = raw.str.match(_RE_ISO_NAIVE_T).fillna(False)
    if mask.any():
        parsed.loc[mask] = pd.to_datetime(raw[mask], format="%Y-%m-%dT%H:%M:%S", utc=True, errors="coerce")
        assumed.loc[mask] = True

    mask = raw.str.match(_RE_ISO_NAIVE_SPACE).fillna(False)
    if mask.any():
        parsed.loc[mask] = pd.to_datetime(raw[mask], format="%Y-%m-%d %H:%M:%S", utc=True, errors="coerce")
        assumed.loc[mask] = True

    mask = raw.str.match(_RE_ISO_OFFSET).fillna(False)
    if mask.any():
        parsed.loc[mask] = pd.to_datetime(raw[mask], format="ISO8601", utc=True, errors="coerce")

    return parsed, assumed, parsed.isna()


def _numeric(raw: pd.Series) -> pd.Series:
    return pd.to_numeric(raw.str.strip(), errors="coerce")


def iso_z(value: Any) -> Optional[str]:
    """Format a timestamp as ISO-8601 UTC with a trailing Z."""
    if value is None or value is pd.NaT or (isinstance(value, float) and np.isnan(value)):
        return None
    return pd.Timestamp(value).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _text_series(value: str, index: pd.Index) -> pd.Series:
    return pd.Series([value] * len(index), index=index, dtype="object")


def _non_empty_join(*parts: pd.Series) -> pd.Series:
    """Join non-empty strings per row with '; ', avoiding stray separators."""
    if not parts:
        return pd.Series(dtype="object")
    result = parts[0]
    for part in parts[1:]:
        result = result.str.cat(part, sep="; ")
    return result.str.replace(r"(?:;\s*)+", "; ", regex=True).str.strip("; ")


def _haversine_km_array(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Vectorised great-circle distance in kilometres (NaN propagates safely)."""
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = phi2 - phi1
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2.0) ** 2
    return 2.0 * 6371.0088 * np.arcsin(np.minimum(1.0, np.sqrt(np.clip(a, 0.0, 1.0))))


def _raw_values(line: int, df: pd.DataFrame) -> Dict[str, Any]:
    """Original values of a source row, for the audit trail."""
    row = df.loc[df["_line"] == line]
    if row.empty:
        return {}
    payload = row.iloc[0].to_dict()
    return {key: (None if isinstance(value, float) and np.isnan(value) else value)
            for key, value in payload.items() if not str(key).startswith("_")}


def _audit(df: pd.DataFrame, line: Any, category: str, reason: str, vessel: Any = None) -> Dict[str, Any]:
    if vessel is None:
        match = df.loc[df["_line"] == line, "MMSI"]
        vessel = str(match.iloc[0]).strip() if not match.empty else ""
    return {
        "sourceLine": int(line),
        "category": category,
        "reason": reason,
        "vesselIdentifier": vessel,
        "rawValues": _raw_values(int(line), df),
    }


def clean_dataframe(
    df: pd.DataFrame,
    config: Optional[CleaningConfig] = None,
    *,
    source: Optional[Dict[str, Any]] = None,
) -> CleaningResult:
    """Clean an AIS dataframe and return records plus a full audit trail.

    Expects the raw-string frame produced by `read_ais_csv` (or an equivalent frame
    with the same columns). The input frame is never modified.
    """
    config = config or CleaningConfig()
    source = dict(source or {})
    total_rows = int(len(df))
    index = df.index

    raw = {column: df[column].astype(str).str.strip()
           for column in (*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS)
           if column in df.columns}
    for column in (*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS):
        raw.setdefault(column, _text_series("", index))

    mmsi_raw = raw["MMSI"].str.strip("'\"").str.strip()
    ts_raw, lat_raw, lon_raw = raw["timestamp"], raw["latitude"], raw["longitude"]

    ts, ts_assumed_utc, ts_unparsed = _parse_timestamps(ts_raw)
    lat, lon = _numeric(lat_raw), _numeric(lon_raw)

    ts_blank, lat_blank, lon_blank = ts_raw.eq(""), lat_raw.eq(""), lon_raw.eq("")
    mmsi_blank = mmsi_raw.eq("")
    lat_non_numeric = lat.isna() & ~lat_blank
    lon_non_numeric = lon.isna() & ~lon_blank
    lat_out_of_range = lat.notna() & ((lat < -90.0) | (lat > 90.0))
    lon_out_of_range = lon.notna() & ((lon < -180.0) | (lon > 180.0))
    null_island = (lat.notna() & lon.notna()
                   & lat.abs().le(config.null_island_tolerance_deg)
                   & lon.abs().le(config.null_island_tolerance_deg))
    mmsi_invalid = ~mmsi_blank & ~mmsi_raw.str.fullmatch(_RE_MMSI).fillna(False)

    reject_category = pd.Series("", index=index, dtype="object")
    reject_reason = pd.Series("", index=index, dtype="object")

    def flag(mask: pd.Series, category: str, reason: pd.Series) -> None:
        """Record the first rejection reason for each row (precedence order)."""
        mask = mask.fillna(False)
        selected = mask & reject_category.eq("")
        if bool(selected.any()):
            reject_category.loc[selected] = category
            reject_reason.loc[selected] = reason.loc[selected]

    # 1. missing required fields -----------------------------------------
    missing_reason = _non_empty_join(
        ts_blank.map({True: "blank timestamp", False: ""}),
        lat_blank.map({True: "blank latitude", False: ""}),
        lon_blank.map({True: "blank longitude", False: ""}),
    ).fillna("blank required field")
    flag(ts_blank | lat_blank | lon_blank, REJECT_MISSING_REQUIRED_FIELD,
         missing_reason.where(missing_reason.ne(""), "blank required field"))

    # 2. malformed timestamps --------------------------------------------
    ts_reason = _text_series("timestamp is not a recognised ISO-8601 instant: ", index) + ts_raw
    flag(ts_unparsed & ~ts_blank, REJECT_MALFORMED_TIMESTAMP, ts_reason)

    # 3. invalid coordinates ---------------------------------------------
    coord_reason = _non_empty_join(
        (lat_non_numeric | lon_non_numeric).map({True: "latitude/longitude is not numeric", False: ""}),
        ("latitude out of range: " + lat_raw).where(lat_out_of_range, ""),
        ("longitude out of range: " + lon_raw).where(lon_out_of_range, ""),
        null_island.map({True: "null-island position (0, 0)", False: ""}),
    )
    flag(lat_non_numeric | lon_non_numeric | lat_out_of_range | lon_out_of_range | null_island,
         REJECT_INVALID_COORDINATE, coord_reason)

    # 4./5. vessel identifiers -------------------------------------------
    flag(mmsi_blank, REJECT_MISSING_IDENTIFIER, _text_series("blank MMSI", index))
    flag(mmsi_invalid, REJECT_INVALID_IDENTIFIER,
         _text_series("MMSI is not 9 digits: ", index) + mmsi_raw)

    rejected_mask = reject_category.ne("")

    # 6. duplicates (considered only among rows that survived the checks above) --
    survivors = df.loc[~rejected_mask].copy()
    survivors["_mmsi"] = mmsi_raw.loc[~rejected_mask]
    survivors["_ts"] = ts.loc[~rejected_mask]
    survivors["_lat"] = lat.loc[~rejected_mask]
    survivors["_lon"] = lon.loc[~rejected_mask]
    survivors["_assumed_utc"] = ts_assumed_utc.loc[~rejected_mask]

    payload_columns = [column for column in survivors.columns if not column.startswith("_")]
    duplicate_key = ["_mmsi", "_ts", "_lat", "_lon", *payload_columns]
    survivors["_first_line"] = survivors.groupby(duplicate_key, sort=False, dropna=False)["_line"].transform("min")
    is_duplicate = survivors.duplicated(subset=duplicate_key, keep="first")

    unique = survivors.loc[~is_duplicate].copy()

    # 7. impossible speed (only among unique rows) ------------------------
    unique = unique.sort_values(["_ts", "_mmsi", "_line"], kind="stable")
    grouped = unique.groupby("_mmsi", sort=False)
    prev_ts = grouped["_ts"].shift(1)
    prev_lat = grouped["_lat"].shift(1)
    prev_lon = grouped["_lon"].shift(1)
    elapsed_s = (unique["_ts"] - prev_ts).dt.total_seconds().to_numpy(dtype="float")
    distance_km = _haversine_km_array(
        prev_lat.to_numpy(dtype="float"), prev_lon.to_numpy(dtype="float"),
        unique["_lat"].to_numpy(dtype="float"), unique["_lon"].to_numpy(dtype="float"),
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        screening_implied_kn = np.where(
            elapsed_s > 0, (distance_km / (elapsed_s / 3600.0)) / KNOTS_TO_KMH, np.nan
        )
    suspicious_vessels = set(
        unique.loc[screening_implied_kn > config.max_plausible_speed_kn, "_mmsi"].tolist()
    )

    # Exact resolution must be ITERATIVE: rejecting one record changes the record its
    # successor has to be compared with. One bad record would otherwise mark two
    # neighbouring steps as impossible (in and out), and the innocent record on the far
    # side would be rejected as well. The iterative pass therefore runs only for the
    # vessels the vectorised screen flagged, so the common case stays vectorised.
    final_implied_kn = np.full(len(unique), np.nan, dtype=float)
    final_distance_km = np.full(len(unique), np.nan, dtype=float)
    prev_lines = np.full(len(unique), -1, dtype=np.int64)
    impossible = np.zeros(len(unique), dtype=bool)
    position_of = {label: position for position, label in enumerate(unique.index)}
    for mmsi, group in unique.groupby("_mmsi", sort=False):
        if mmsi not in suspicious_vessels:
            continue
        labels = group.index.to_numpy()
        group_ts = group["_ts"].to_numpy()
        group_lat = group["_lat"].to_numpy(dtype=float)
        group_lon = group["_lon"].to_numpy(dtype=float)
        group_lines = group["_line"].to_numpy(dtype=np.int64)
        last = 0
        for offset in range(1, len(labels)):
            elapsed = (group_ts[offset] - group_ts[last]) / np.timedelta64(1, "s")
            if elapsed <= 0:
                # Two records sharing a timestamp: no speed can be inferred. Those rows
                # are reported separately as conflicting positions, never as impossible.
                last = offset
                continue
            local_distance = haversine_km(
                group_lat[last], group_lon[last], group_lat[offset], group_lon[offset]
            )
            local_speed = (local_distance / (elapsed / 3600.0)) / KNOTS_TO_KMH
            slot = position_of[labels[offset]]
            final_implied_kn[slot] = local_speed
            final_distance_km[slot] = local_distance
            if local_speed > config.max_plausible_speed_kn:
                impossible[slot] = True
                prev_lines[slot] = int(group_lines[last])
            else:
                last = offset
    unique["_implied_kn"] = final_implied_kn
    unique["_distance_km"] = final_distance_km
    unique["_prev_line"] = prev_lines

    kept = unique.loc[~impossible]

    # conflicting positions sharing one timestamp (a quality signal, not a rejection)
    conflicts = (
        kept.groupby(["_mmsi", "_ts"], sort=False, dropna=False)["_lat"].transform("size").gt(1)
        & kept.groupby(["_mmsi", "_ts"], sort=False, dropna=False)["_lat"].transform("nunique").gt(1)
    )
    return _assemble(
        df=df, config=config, source=source, total_rows=total_rows,
        reject_category=reject_category, reject_reason=reject_reason,
        survivors=survivors, is_duplicate=is_duplicate, unique=unique,
        impossible=impossible, kept=kept, conflicts=conflicts, raw=raw,
    )


def _assemble(
    *, df: pd.DataFrame, config: CleaningConfig, source: Dict[str, Any], total_rows: int,
    reject_category: pd.Series, reject_reason: pd.Series, survivors: pd.DataFrame,
    is_duplicate: pd.Series, unique: pd.DataFrame, impossible: np.ndarray,
    kept: pd.DataFrame, conflicts: pd.Series, raw: Dict[str, pd.Series],
) -> CleaningResult:
    """Build records, vessel summaries, audit entries and statistics."""
    rejected: List[Dict[str, Any]] = []

    # --- row rejections (checks 1-5) --------------------------------------
    rejected_rows = reject_category.ne("")
    for line, category, reason in zip(
        df.loc[rejected_rows, "_line"].tolist(),
        reject_category.loc[rejected_rows].tolist(),
        reject_reason.loc[rejected_rows].tolist(),
    ):
        rejected.append(_audit(df, line, category, reason))

    # --- duplicates -------------------------------------------------------
    for line, first, mmsi in zip(
        survivors.loc[is_duplicate, "_line"].tolist(),
        survivors.loc[is_duplicate, "_first_line"].tolist(),
        survivors.loc[is_duplicate, "_mmsi"].tolist(),
    ):
        rejected.append(_audit(
            df, line, REJECT_DUPLICATE,
            f"identical to source line {int(first)} on every field "
            "(MMSI, timestamp, position, SOG, COG and all optional fields)",
            mmsi,
        ))

    # --- impossible speed ------------------------------------------------
    prev_line = unique["_prev_line"]
    for line, mmsi, kn, previous, distance in zip(
        unique.loc[impossible, "_line"].tolist(),
        unique.loc[impossible, "_mmsi"].tolist(),
        unique.loc[impossible, "_implied_kn"].tolist(),
        prev_line.loc[impossible].tolist(),
        unique.loc[impossible, "_distance_km"].tolist(),
    ):
        rejected.append(_audit(
            df, line, REJECT_IMPOSSIBLE_SPEED,
            f"implied speed {kn:.1f} kn over {distance:.1f} km from source line {int(previous)} "
            f"exceeds the configured max_plausible_speed_kn={config.max_plausible_speed_kn} "
            "(prototype threshold, not a physical constant)",
            mmsi,
        ))
    rejected.sort(key=lambda entry: entry["sourceLine"])

    # --- per-vessel value cleanup ---------------------------------------
    kept_index = kept.index
    sog_raw = raw["SOG"].loc[kept_index]
    cog_raw = raw["COG"].loc[kept_index]
    heading_raw = raw["heading"].loc[kept_index]
    nav_raw = raw["navigationStatus"].loc[kept_index]
    sog, cog, heading, nav = _numeric(sog_raw), _numeric(cog_raw), _numeric(heading_raw), _numeric(nav_raw)

    sog_blank, cog_blank, heading_blank, nav_blank = (
        sog_raw.eq(""), cog_raw.eq(""), heading_raw.eq(""), nav_raw.eq(""))
    sog_bad = ((sog.isna() & ~sog_blank) | (sog.notna() & ((sog < 0.0) | (sog > 150.0))))
    cog_bad = ((cog.isna() & ~cog_blank) | (cog.notna() & ((cog < 0.0) | (cog >= 360.0))))
    heading_bad = ((heading.isna() & ~heading_blank)
                   | (heading.notna() & ((heading < 0.0) | (heading > 359.0) | (heading % 1 != 0))))
    nav_bad = ((nav.isna() & ~nav_blank) | (nav.notna() & ((nav < 0.0) | (nav > 15.0) | (nav % 1 != 0))))
    sentinel_sog = sentinel_cog = sentinel_heading = pd.Series(False, index=kept_index)
    if config.treat_not_available_sentinels:
        sentinel_sog = sog.notna() & sog.eq(AIS_NOT_AVAILABLE_SOG_KN)
        sentinel_cog = cog.notna() & cog.eq(AIS_NOT_AVAILABLE_COG_DEG)
        sentinel_heading = heading.notna() & heading.eq(AIS_NOT_AVAILABLE_HEADING_DEG)

    # --- arrays for the record loop -------------------------------------
    lines = kept["_line"].to_numpy(dtype=np.int64)
    mmsis = kept["_mmsi"].to_numpy(dtype=object)
    stamps = kept["_ts"].to_numpy()
    lats = kept["_lat"].to_numpy(dtype=float)
    lons = kept["_lon"].to_numpy(dtype=float)
    assumed_utc = kept["_assumed_utc"].to_numpy(dtype=bool)
    conflict_rows = conflicts.to_numpy(dtype=bool)
    names = raw["vesselName"].loc[kept_index].to_numpy(dtype=object)
    imos = raw["IMO"].loc[kept_index].to_numpy(dtype=object)
    types_raw = raw["vesselType"].loc[kept_index].to_numpy(dtype=object)
    labels = raw["datasetLabel"].loc[kept_index].to_numpy(dtype=object)
    vessel_types = _numeric(raw["vesselType"].loc[kept_index]).to_numpy(dtype=float)
    sog_values = sog.mask(sog_bad | sentinel_sog).to_numpy(dtype=float)
    cog_values = cog.mask(cog_bad | sentinel_cog).to_numpy(dtype=float)
    heading_values = heading.mask(heading_bad | sentinel_heading).to_numpy(dtype=float)
    nav_values = nav.mask(nav_bad).to_numpy(dtype=float)
    # Positional (numpy) copies of the blank-field masks. Inside the record loop rows
    # are addressed by POSITION, and `Series[int]` would be a LABEL lookup - which
    # would either raise or silently read the wrong row.
    sog_blank_arr = sog_blank.to_numpy(dtype=bool)
    cog_blank_arr = cog_blank.to_numpy(dtype=bool)
    heading_blank_arr = heading_blank.to_numpy(dtype=bool)
    nav_blank_arr = nav_blank.to_numpy(dtype=bool)

    removed_arrays = {
        REMOVE_INVALID_SPEED: (sog_bad & ~sentinel_sog).to_numpy(dtype=bool),
        REMOVE_INVALID_COURSE: (cog_bad & ~sentinel_cog).to_numpy(dtype=bool),
        REMOVE_INVALID_HEADING: (heading_bad & ~sentinel_heading).to_numpy(dtype=bool),
        REMOVE_INVALID_NAVIGATION_STATUS: nav_bad.to_numpy(dtype=bool),
        REMOVE_NOT_AVAILABLE: (sentinel_sog | sentinel_cog | sentinel_heading).to_numpy(dtype=bool),
    }
    removed_reasons = {
        REMOVE_INVALID_SPEED: "speed over ground is negative or above 150 kn; value removed",
        REMOVE_INVALID_COURSE: "course over ground outside [0, 360); value removed",
        REMOVE_INVALID_HEADING: "heading is not an integer in [0, 359]; value removed",
        REMOVE_INVALID_NAVIGATION_STATUS: "navigation status is not an integer in [0, 15]; value removed",
        REMOVE_NOT_AVAILABLE: "AIS 'not available' sentinel value replaced by null",
    }

    records: List[Dict[str, Any]] = []
    removed_values: List[Dict[str, Any]] = []
    warning_by_category: Counter = Counter()
    removed_by_category: Counter = Counter()
    vessel_stats: Dict[str, Dict[str, Any]] = {}
    rows_with_warnings = 0
    rows_with_removed_values = 0
    synthetic_records = 0

    for position in range(len(lines)):
        line = int(lines[position])
        mmsi = str(mmsis[position]).strip()
        stamp = stamps[position]
        name = str(names[position]).strip()
        imo = str(imos[position]).strip()
        type_text = str(types_raw[position]).strip()
        label = str(labels[position]).strip()
        nav_value = nav_values[position]

        warnings: List[str] = []
        if (sog_blank_arr[position] or cog_blank_arr[position] or heading_blank_arr[position]
                or nav_blank_arr[position] or type_text == "" or name == "" or imo == ""):
            warnings.append(WARN_MISSING_OPTIONAL)
        if assumed_utc[position] and config.assume_naive_timestamp_is_utc:
            warnings.append(WARN_ASSUMED_UTC)
        if conflict_rows[position]:
            warnings.append(WARN_CONFLICTING_TIMESTAMP)
        if name == "":
            warnings.append(WARN_MISSING_NAME)
        vessel_type: Optional[int] = None
        if type_text != "" and not np.isnan(vessel_types[position]) and 0 <= vessel_types[position] <= 99:
            vessel_type = int(vessel_types[position])
        elif type_text != "":
            warnings.append(WARN_UNKNOWN_VESSEL_TYPE)
        if imo != "" and (not _RE_IMO_PATTERN.match(imo) or not _imo_check_digit_ok(imo)):
            warnings.append(WARN_INVALID_IMO)

        for category, flags in removed_arrays.items():
            if flags[position]:
                removed_values.append({
                    "sourceLine": line, "category": category, "reason": removed_reasons[category],
                    "vesselIdentifier": mmsi,
                    "rawValue": {
                        REMOVE_INVALID_SPEED: sog_raw.iloc[position],
                        REMOVE_INVALID_COURSE: cog_raw.iloc[position],
                        REMOVE_INVALID_HEADING: heading_raw.iloc[position],
                        REMOVE_INVALID_NAVIGATION_STATUS: nav_raw.iloc[position],
                        REMOVE_NOT_AVAILABLE: _sentinel_raw(position, sog_raw, cog_raw, heading_raw),
                    }[category],
                })
                removed_by_category[category] += 1
                # The record itself must say that a value was removed from it, so that a
                # later phase can never read a null value as "the vessel reported nothing".
                warnings.append(category)

        if warnings:
            rows_with_warnings += 1
            for warning in warnings:
                warning_by_category[warning] += 1
        if any(flags[position] for flags in removed_arrays.values()):
            rows_with_removed_values += 1
        if label == SYNTHETIC_LABEL:
            synthetic_records += 1

        stamp_iso = pd.Timestamp(stamp).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
        record = {
            "mmsi": mmsi,
            "imo": imo or None,
            "vesselName": name or None,
            "vesselType": vessel_type,
            "timestamp": stamp_iso,
            "epochSeconds": int(pd.Timestamp(stamp).timestamp()),
            "latitude": round(float(lats[position]), 6),
            "longitude": round(float(lons[position]), 6),
            "sogKn": None if np.isnan(sog_values[position]) else round(float(sog_values[position]), 3),
            "cogDeg": None if np.isnan(cog_values[position]) else round(float(cog_values[position]), 1),
            "headingDeg": None if np.isnan(heading_values[position]) else int(heading_values[position]),
            "navigationStatus": None if np.isnan(nav_value) else int(nav_value),
            "datasetLabel": label or None,
            "synthetic": label == SYNTHETIC_LABEL,
            "sourceLine": line,
            "warnings": warnings,
        }
        records.append(record)

        vessel = vessel_stats.setdefault(mmsi, {
            "mmsi": mmsi, "vesselName": name or None, "vesselType": vessel_type,
            "records": 0, "firstTimestamp": stamp_iso, "lastTimestamp": stamp_iso,
            "warningRecords": 0, "notes": [],
        })
        vessel["records"] += 1
        vessel["lastTimestamp"] = stamp_iso
        if warnings:
            vessel["warningRecords"] += 1
        if vessel["vesselName"] is None and name:
            vessel["vesselName"] = name

    removed_values.sort(key=lambda entry: (entry["sourceLine"], entry["category"]))
    vessels = [vessel_stats[key] for key in sorted(vessel_stats)]

    # --- statistics -------------------------------------------------------
    rejection_by_category = Counter(entry["category"] for entry in rejected)
    # Ordering: compare each kept record's position among the kept rows in the source
    # file with its position in the sorted output. (Comparing raw file line numbers
    # would count every row after a rejected row as "reordered".)
    file_order = kept["_order"].to_numpy(dtype=np.int64)
    file_position = np.empty(len(file_order), dtype=np.int64)
    file_position[np.argsort(file_order, kind="stable")] = np.arange(len(file_order), dtype=np.int64)
    rows_reordered = int(np.sum(file_position != np.arange(len(file_order), dtype=np.int64)))
    labels_present = sorted({value for value in raw["datasetLabel"].astype(str).str.strip().unique() if value})
    counts = {
        "rowsIn": total_rows,
        "records": len(records),
        "rowsRejected": len(rejected),
        "rowsReordered": rows_reordered,
        "rowsUnchangedPosition": len(records) - rows_reordered,
        "rowsWithWarnings": rows_with_warnings,
        "warningCount": int(sum(warning_by_category.values())),
        "rowsWithRemovedValues": rows_with_removed_values,
        "valuesRemoved": len(removed_values),
        "vessels": len(vessels),
        "duplicateRecordsRejected": rejection_by_category.get(REJECT_DUPLICATE, 0),
        "syntheticLabelledRecords": synthetic_records,
    }
    stamps_series = kept["_ts"]
    statistics = {
        "counts": counts,
        "rejectionByCategory": {key: rejection_by_category[key] for key in sorted(rejection_by_category)},
        "rejectionByVessel": _counter_by_vessel(rejected),
        "removedValueByCategory": {key: removed_by_category[key] for key in sorted(removed_by_category)},
        "warningByCategory": {key: warning_by_category[key] for key in sorted(warning_by_category)},
        "timeRange": {
            "start": stamps_series.min().tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ") if len(stamps_series) else None,
            "end": stamps_series.max().tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ") if len(stamps_series) else None,
        },
        "reportingIntervalSeconds": _reporting_interval_seconds(kept),
        "cleaningIsAuditable": True,
        "syntheticDataPresent": synthetic_records > 0,
    }
    return CleaningResult(
        records=records, vessels=vessels, rejected=rejected, removed_values=removed_values,
        statistics=statistics, source=source, config=config.describe(),
        warnings=_result_warnings(source, statistics, labels_present),
        notes=_result_notes(config, rows_reordered),
    )


def _imo_check_digit_ok(imo: str) -> bool:
    """Validate the IMO number check digit (digits weighted 7,6,5,4,3,2; sum mod 10).

    A failure here does not reject the row: the position data is still usable. It is
    reported as a warning so an investigator can decide whether the identity is
    trustworthy.
    """
    if not _RE_IMO_PATTERN.match(imo):
        return False
    weights = (7, 6, 5, 4, 3, 2)
    total = sum(int(ch) * weight for ch, weight in zip(imo[:6], weights))
    return total % 10 == int(imo[6])


def _sentinel_raw(position: int, *columns: pd.Series) -> Optional[str]:
    """Describe which AIS 'not available' sentinel caused a value to be nulled."""
    expected = {
        "SOG": (AIS_NOT_AVAILABLE_SOG_KN,),
        "COG": (AIS_NOT_AVAILABLE_COG_DEG,),
        "heading": (AIS_NOT_AVAILABLE_HEADING_DEG,),
    }
    found: List[str] = []
    for column in columns:
        name = column.name
        value = str(column.iloc[position]).strip()
        if value == "" or name not in expected:
            continue
        try:
            if float(value) in expected[name]:
                found.append(f"{name}={value}")
        except ValueError:
            continue
    return "; ".join(found) or None


def _counter_by_vessel(entries: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counter: Counter = Counter(str(entry.get("vesselIdentifier", "") or "unknown") for entry in entries)
    return {key: counter[key] for key in sorted(counter)}


def _reporting_interval_seconds(kept: pd.DataFrame) -> Dict[str, Any]:
    """Typical interval between consecutive records of the same vessel.

    This is a DESCRIPTIVE statistic about recording density, reported so an
    investigator knows how dense the evidence is. It is NOT AIS gap analysis
    (Phase 9): nothing here is treated as missing, suspicious or unusual.
    """
    note = "descriptive recording density only - not gap analysis"
    if kept.empty:
        return {"modalSeconds": None, "perVesselSeconds": {}, "note": note}
    frame = kept[["_mmsi", "_ts"]].copy()
    frame["deltaSeconds"] = frame["_ts"].diff().dt.total_seconds()
    frame.loc[frame["_mmsi"].ne(frame["_mmsi"].shift(1)), "deltaSeconds"] = np.nan
    per_vessel: Dict[str, int] = {}
    for mmsi, group in frame.groupby("_mmsi", sort=True):
        deltas = group["deltaSeconds"].dropna()
        if len(deltas):
            per_vessel[str(mmsi)] = int(deltas.mode().iloc[0])
    overall = frame["deltaSeconds"].dropna()
    return {
        "modalSeconds": int(overall.mode().iloc[0]) if len(overall) else None,
        "perVesselSeconds": per_vessel,
        "note": note,
    }


def _result_warnings(source: Dict[str, Any], statistics: Dict[str, Any], labels_present: Sequence[str]) -> List[str]:
    """Dataset-level warnings for the UI: provenance, labelling and cleaning impact."""
    warnings: List[str] = []
    counts = statistics.get("counts", {})
    if statistics.get("syntheticDataPresent"):
        warnings.append(
            f"{SYNTHETIC_UI_WARNING} - synthetic AIS is demonstration data and is never "
            "presented as real-world evidence"
        )
    unexpected = [label for label in labels_present if label != SYNTHETIC_LABEL]
    if unexpected:
        warnings.append(
            "records carry dataset label(s) that are not recognised as synthetic: "
            + ", ".join(unexpected)
        )
    if not source.get("synthetic"):
        warnings.append("source is not marked as synthetic; verify the provider and its labelling")
    if counts.get("rowsRejected"):
        warnings.append(
            f"{counts['rowsRejected']} row(s) were rejected during cleaning and are listed in "
            "rejected[] with reasons - nothing was dropped silently"
        )
    if counts.get("rowsWithRemovedValues"):
        warnings.append(
            f"{counts['valuesRemoved']} individual value(s) were removed from "
            f"{counts['rowsWithRemovedValues']} kept row(s); see removedValues[]"
        )
    return warnings


def _result_notes(config: CleaningConfig, rows_reordered: int) -> List[str]:
    """Method notes that must travel with the result (prototype honesty)."""
    notes = [
        "Cleaning never deletes a suspicious record: rejected rows are returned in full under "
        "`rejected`, each with its source line number and raw values, and counts per category.",
        "A valid row that contained one impossible value is kept at its original position with "
        "that value set to null and listed under `removedValues`.",
        "A removed value is reported twice on purpose: in the record's own `warnings` list and in "
        "`removedValues[]` with the raw value, so downstream phases never mistake a null for "
        "\"the vessel reported nothing\".",
        f"The impossible-speed threshold is a configurable PROTOTYPE value "
        f"(max_plausible_speed_kn={config.max_plausible_speed_kn}), not a physical constant.",
        "Every record keeps its source line number so any later conclusion can be traced to the "
        "raw file.",
        "Rejection categories are assigned by precedence (see the module docstring); a rejected "
        "row still carries all of its raw values in the audit entry.",
    ]
    if rows_reordered:
        notes.append(
            f"Records were time-sorted for processing; {rows_reordered} record(s) sit at a "
            "different position than in the source file (counts.rowsReordered)."
        )
    return notes


# ===========================================================================
# Public API
# ===========================================================================
CLEANED_COLUMNS = (
    "mmsi", "imo", "vesselName", "vesselType", "timestamp", "latitude", "longitude",
    "sogKn", "cogDeg", "headingDeg", "navigationStatus", "datasetLabel", "sourceLine",
)


def clean_csv(
    path: Path,
    config: Optional[CleaningConfig] = None,
    *,
    provider: str = "DemoAISProvider",
    synthetic: Optional[bool] = None,
) -> CleaningResult:
    """Read a raw AIS CSV and clean it.

    `synthetic` defaults to None, meaning "infer from the data": if any row carries
    the synthetic demonstration label the source is marked synthetic, so demo data
    cannot be presented as real-world evidence by accident.
    """
    path = Path(path)
    df = read_ais_csv(path)
    label_column = df["datasetLabel"].astype(str).str.strip() if "datasetLabel" in df.columns \
        else pd.Series("", index=df.index, dtype="object")
    labels_present = sorted({value for value in label_column.unique() if value})
    inferred = SYNTHETIC_LABEL in labels_present
    source = {
        "provider": provider,
        "uri": str(path),
        "synthetic": inferred if synthetic is None else bool(synthetic),
        "syntheticInferredFromData": synthetic is None,
        "datasetLabels": labels_present,
    }
    return clean_dataframe(df, config, source=source)


def clean_demo_case(settings: Optional[Any] = None) -> CleaningResult:
    """Clean the bundled synthetic CASE-001 extract (DEMO MODE, no credentials)."""
    settings = settings or app_config.get_settings()
    return clean_csv(
        settings.demo_ais_csv,
        settings.ais_cleaning_config(),
        provider="DemoAISProvider",
        synthetic=True,
    )


def write_cleaned_csv(path: Path, records: Sequence[Dict[str, Any]]) -> None:
    """Write cleaned records to CSV (one row per positional report)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CLEANED_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({column: _csv_value(record.get(column)) for column in CLEANED_COLUMNS})


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def summarise_for_report(result: CleaningResult) -> Dict[str, Any]:
    """Compact, report-ready summary (used by the API and the final report in Phase 18).

    Contains only what the data does and does not contain - no conclusion about any
    vessel.
    """
    counts = result.statistics.get("counts", {})
    return {
        "dataSource": result.data_source,
        "synthetic": result.synthetic,
        "rowsIn": counts.get("rowsIn"),
        "rowsOut": counts.get("records"),
        "rowsRejected": counts.get("rowsRejected"),
        "rejectionByCategory": result.statistics.get("rejectionByCategory", {}),
        "removedValueByCategory": result.statistics.get("removedValueByCategory", {}),
        "warningByCategory": result.statistics.get("warningByCategory", {}),
        "vessels": counts.get("vessels"),
        "timeRange": result.statistics.get("timeRange", {}),
        "reportingIntervalSeconds": result.statistics.get("reportingIntervalSeconds", {}),
        "warnings": result.warnings,
        "notes": result.notes,
        "config": result.config,
    }


# ===========================================================================
# Command line interface
# ===========================================================================
def print_cleaning_summary(result: CleaningResult) -> None:
    counts = result.statistics.get("counts", {})
    line = "=" * 100
    print(line)
    print("ABYSS - AIS cleaning report (Phase 3)")
    print(f"  source        : {result.source.get('uri')}")
    print(f"  provider      : {result.data_source}")
    print(f"  synthetic     : {result.synthetic}")
    print(f"  module        : ais.cleaning {MODULE_VERSION}")
    print(line)
    print("COUNTS")
    print(f"  rows in                         : {counts.get('rowsIn')}")
    print(f"  records (kept, usable)          : {counts.get('records')}")
    print(f"  rows rejected                   : {counts.get('rowsRejected')}")
    print(f"  rows with warnings              : {counts.get('rowsWithWarnings')}")
    print(f"  rows with a value removed       : {counts.get('rowsWithRemovedValues')}")
    print(f"  individual values removed       : {counts.get('valuesRemoved')}")
    print(f"  vessels                         : {counts.get('vessels')}")
    print(f"  rows reordered (time sorting)   : {counts.get('rowsReordered')}")
    print(f"  records labelled synthetic      : {counts.get('syntheticLabelledRecords')}")
    time_range = result.statistics.get("timeRange", {})
    print(f"  time range                      : {time_range.get('start')} -> {time_range.get('end')}")
    interval = result.statistics.get("reportingIntervalSeconds", {})
    print(f"  typical reporting interval      : {interval.get('modalSeconds')} s "
          f"({interval.get('note')})")
    print()
    print("REJECTIONS BY CATEGORY (each row is kept in the audit trail, never deleted)")
    by_category = result.statistics.get("rejectionByCategory", {})
    if not by_category:
        print("  (none)")
    for category, count in by_category.items():
        print(f"  {category:<26} {count:>4}")
    print()
    print("REJECTED ROWS (first 15)")
    for entry in result.rejected[:15]:
        print(f"  line {entry['sourceLine']:>5}  {entry['category']:<24} {entry['vesselIdentifier']:<10} "
              f"{entry['reason']}")
    if len(result.rejected) > 15:
        print(f"  ... and {len(result.rejected) - 15} more (see the JSON output for the full audit trail)")
    print()
    print("VALUES REMOVED FROM KEPT ROWS")
    if not result.removed_values:
        print("  (none)")
    for entry in result.removed_values[:15]:
        print(f"  line {entry['sourceLine']:>5}  {entry['category']:<24} {entry['vesselIdentifier']:<10} "
              f"raw={entry['rawValue']}  {entry['reason']}")
    if len(result.removed_values) > 15:
        print(f"  ... and {len(result.removed_values) - 15} more")
    print()
    print("WARNINGS BY CATEGORY")
    warnings_by_category = result.statistics.get("warningByCategory", {})
    if not warnings_by_category:
        print("  (none)")
    for category, count in warnings_by_category.items():
        print(f"  {category:<28} {count:>4}")
    print()
    print("DATASET-LEVEL WARNINGS")
    for warning in result.warnings:
        print(f"  - {warning}")
    print()
    print("METHOD NOTES")
    for note in result.notes:
        print(f"  - {note}")
    print(line)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean an ABYSS AIS extract and report a complete audit trail.",
    )
    parser.add_argument("--input", default=None, help="raw AIS CSV (default: the synthetic CASE-001 demo extract)")
    parser.add_argument("--json", dest="json_out", default=None, help="write the full result (records + audit) as JSON")
    parser.add_argument("--out-cleaned", dest="out_cleaned", default=None, help="write cleaned records as CSV")
    parser.add_argument("--max-speed-kn", dest="max_speed_kn", type=float, default=None,
                       help="impossible-speed threshold in knots (prototype default 60)")
    parser.add_argument("--provider", default=None, help="provider name recorded in the result")
    parser.add_argument("--quiet", action="store_true", help="suppress the printed summary")
    args = parser.parse_args(argv)

    settings = app_config.get_settings()
    config = settings.ais_cleaning_config()
    if args.max_speed_kn is not None:
        config = CleaningConfig(
            max_plausible_speed_kn=args.max_speed_kn,
            null_island_tolerance_deg=config.null_island_tolerance_deg,
            treat_not_available_sentinels=config.treat_not_available_sentinels,
            assume_naive_timestamp_is_utc=config.assume_naive_timestamp_is_utc,
            max_audit_records=config.max_audit_records,
        )

    if args.input:
        result = clean_csv(Path(args.input), config, provider=args.provider or "FileAISProvider",
                           synthetic=None)
    else:
        result = clean_csv(settings.demo_ais_csv, config,
                           provider=args.provider or "DemoAISProvider", synthetic=True)

    if args.out_cleaned:
        write_cleaned_csv(Path(args.out_cleaned), result.records)
    if args.json_out:
        payload = result.to_dict()
        payload["summary"] = summarise_for_report(result)
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.quiet:
        counts = result.statistics.get("counts", {})
        print(f"cleaned {counts.get('rowsIn')} rows -> {counts.get('records')} records, "
              f"{counts.get('rowsRejected')} rejected, {counts.get('valuesRemoved')} value(s) removed "
              f"({counts.get('vessels')} vessels)")
    else:
        print_cleaning_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
