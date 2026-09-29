"""Real metocean data loader for ABYSS forensic intelligence.

Loads:
1. NOAA Near Real Time Geostrophic Currents NetCDF (u_current, v_current).
2. NDBC standard meteorological tables (buoy wind observations).

Normalizes both into the existing ABYSS `EnvironmentalField` representation
with explicit timestamp handling, spatial bounds, and forensic provenance.
Never invents data; reports missing variables/timestamps honestly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.hindcast.environmental import EnvironmentalField, EnvironmentalFieldError


@dataclass
class WindObservation:
    """Single-station meteorological observation from NDBC."""

    timestamp_iso: str
    epoch_seconds: float
    wdir_deg: float
    wspd_ms: float
    u_wind_ms: float
    v_wind_ms: float
    station_id: str


@dataclass
class MetoceanProvenance:
    """Provenance audit trail for environmental forcing data."""

    provider: str
    dataset: str
    variables: List[str]
    time_coverage: List[str]
    spatial_extent: Dict[str, float]
    synthetic: bool = False
    source_path: Optional[str] = None
    wind_available: bool = False
    current_available: bool = False
    wind_station: Optional[str] = None
    notes: List[str] = dc_field(default_factory=list)
    warnings: List[str] = dc_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "dataset": self.dataset,
            "variables": list(self.variables),
            "time_coverage": list(self.time_coverage),
            "spatial_extent": dict(self.spatial_extent),
            "synthetic": self.synthetic,
            "source_path": self.source_path,
            "wind_available": self.wind_available,
            "current_available": self.current_available,
            "wind_station": self.wind_station,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
        }


def parse_ndbc_timestamp(parts: Sequence[str]) -> Tuple[datetime, float]:
    """Parse #YY MM DD hh mm from NDBC table row."""
    year = int(parts[0])
    month = int(parts[1])
    day = int(parts[2])
    hour = int(parts[3])
    minute = int(parts[4])
    dt = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    return dt, dt.timestamp()


def meteorological_to_uv(wspd_ms: float, wdir_deg: float) -> Tuple[float, float]:
    """Convert meteorological wind (FROM direction) to oceanographic u, v (m/s).

    Wind from North (0 deg) blows toward South -> v < 0.
    Wind from East (90 deg) blows toward West -> u < 0.
    """
    rad = math.radians(wdir_deg % 360.0)
    u = -wspd_ms * math.sin(rad)
    v = -wspd_ms * math.cos(rad)
    return round(u, 4), round(v, 4)


def load_ndbc_table(path: Path | str, station_id: str = "42055") -> List[WindObservation]:
    """Parse NDBC realtime2 or historical stdmet text table."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"NDBC table not found: {p}")

    records: List[WindObservation] = []
    with p.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 7:
                continue
            wdir_str, wspd_str = parts[5], parts[6]
            if wdir_str == "MM" or wspd_str == "MM":
                continue
            try:
                dt, epoch = parse_ndbc_timestamp(parts[:5])
                wdir = float(wdir_str)
                wspd = float(wspd_str)
            except (ValueError, TypeError):
                continue
            u, v = meteorological_to_uv(wspd, wdir)
            records.append(
                WindObservation(
                    timestamp_iso=dt.isoformat().replace("+00:00", "Z"),
                    epoch_seconds=epoch,
                    wdir_deg=wdir,
                    wspd_ms=wspd,
                    u_wind_ms=u,
                    v_wind_ms=v,
                    station_id=station_id,
                )
            )

    records.sort(key=lambda r: r.epoch_seconds)
    return records


def find_nearest_wind(
    records: Sequence[WindObservation],
    target_epoch: float,
    max_delta_seconds: float = 3600.0 * 6,
) -> Optional[WindObservation]:
    """Find wind observation nearest to target_epoch within max_delta_seconds."""
    if not records:
        return None
    best: Optional[WindObservation] = None
    best_delta = float("inf")
    for r in records:
        delta = abs(r.epoch_seconds - target_epoch)
        if delta < best_delta:
            best_delta = delta
            best = r
    if best is not None and best_delta <= max_delta_seconds:
        return best
    return None


def load_noaa_currents_netcdf(
    path: Path | str,
    wind_record: Optional[WindObservation] = None,
    windage: float = 0.035,
) -> Tuple[EnvironmentalField, MetoceanProvenance]:
    """Load a real NOAA Near Real Time Geostrophic Currents NetCDF file."""
    try:
        import xarray as xr
    except ImportError as e:
        raise EnvironmentalFieldError("xarray is required to read NetCDF data") from e

    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"NOAA currents file not found: {p}")

    ds = xr.open_dataset(p)

    lat_key = "latitude" if "latitude" in ds.coords else "lat"
    lon_key = "longitude" if "longitude" in ds.coords else "lon"
    if lat_key not in ds.coords or lon_key not in ds.coords:
        raise EnvironmentalFieldError(f"NetCDF missing lat/lon coordinates: {list(ds.coords)}")

    latitudes = [float(x) for x in np.sort(ds[lat_key].values)]
    longitudes = [float(x) for x in np.sort(ds[lon_key].values)]

    if "u_current" not in ds.data_vars or "v_current" not in ds.data_vars:
        raise EnvironmentalFieldError(
            f"NetCDF missing u_current/v_current variables: {list(ds.data_vars)}"
        )

    u_data = ds["u_current"].values
    v_data = ds["v_current"].values

    if u_data.ndim == 3:
        u_slice = u_data[0]
        v_slice = v_data[0]
    elif u_data.ndim == 2:
        u_slice = u_data
        v_slice = v_data
    else:
        raise EnvironmentalFieldError(f"Unexpected u_current dimensions: {u_data.shape}")

    has_nan = bool(np.isnan(u_slice).any() or np.isnan(v_slice).any())
    if has_nan:
        u_slice = np.nan_to_num(u_slice, nan=0.0)
        v_slice = np.nan_to_num(v_slice, nan=0.0)

    u_current_grid = [[float(val) for val in row] for row in u_slice]
    v_current_grid = [[float(val) for val in row] for row in v_slice]

    n_lat = len(latitudes)
    n_lon = len(longitudes)

    warnings: List[str] = []
    notes: List[str] = []
    variables = ["u_current", "v_current"]

    if has_nan:
        warnings.append("NaN values in ocean current grid were replaced with 0.0")

    if wind_record is not None:
        u_wind_grid = [[float(wind_record.u_wind_ms)] * n_lon for _ in range(n_lat)]
        v_wind_grid = [[float(wind_record.v_wind_ms)] * n_lon for _ in range(n_lat)]
        variables.extend(["u_wind", "v_wind"])
        notes.append(
            f"Wind forcing from NDBC buoy {wind_record.station_id} at {wind_record.timestamp_iso}: "
            f"WDIR={wind_record.wdir_deg}deg, WSPD={wind_record.wspd_ms}m/s"
        )
        wind_available = True
    else:
        u_wind_grid = [[0.0] * n_lon for _ in range(n_lat)]
        v_wind_grid = [[0.0] * n_lon for _ in range(n_lat)]
        warnings.append(
            "Wind forcing unavailable for this timestamp. "
            "Drift reflects ocean currents only; windage contribution is zero."
        )
        wind_available = False

    time_coverage: List[str] = []
    if "time" in ds.coords:
        for t in ds["time"].values:
            ts = str(t)
            if "T" in ts:
                ts = ts.split(".")[0] + "Z"
            time_coverage.append(ts)
    if not time_coverage:
        time_coverage = ["unspecified"]

    valid_from = time_coverage[0] if time_coverage else None
    valid_to = time_coverage[-1] if time_coverage else None

    contact = ds.attrs.get("contact", "NOAA")
    data_source = ds.attrs.get("data_source", "Altimeter data")

    provenance = MetoceanProvenance(
        provider=f"NOAA ({contact})",
        dataset=f"AOML Near Real Time Geostrophic Currents ({data_source})",
        variables=variables,
        time_coverage=time_coverage,
        spatial_extent={
            "lat_min": min(latitudes),
            "lat_max": max(latitudes),
            "lon_min": min(longitudes),
            "lon_max": max(longitudes),
        },
        synthetic=False,
        source_path=str(p),
        wind_available=wind_available,
        current_available=True,
        wind_station=wind_record.station_id if wind_record else None,
        notes=notes,
        warnings=warnings,
    )

    field = EnvironmentalField(
        latitudes=latitudes,
        longitudes=longitudes,
        u_current=u_current_grid,
        v_current=v_current_grid,
        u_wind=u_wind_grid,
        v_wind=v_wind_grid,
        windage=windage,
        provider="NOAA AOML NRT Geostrophic Currents",
        synthetic=False,
        dataset_label=p.name,
        valid_from=valid_from,
        valid_to=valid_to,
        time_behaviour="single_snapshot",
        units={"current": "m/s", "wind": "m/s"},
        notes=notes,
        warnings=warnings,
        source_path=str(p),
    )

    return field, provenance
