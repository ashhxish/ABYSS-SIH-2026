"""ABYSS - environmental field loader and drift sampling (Phase 11 input).

PURPOSE
    Load the provider's environmental field (a regular grid of surface current
    and wind vectors) and evaluate the SURFACE DRIFT VELOCITY at any position:

        drift = current + windage * wind          (prototype parametrisation)

    The origin hindcast integrates this velocity backwards in time from the
    observed slick to reconstruct where the oil could have been released.

WHY BILINEAR INTERPOLATION
    The field is published on a coarse grid (0.25 deg in the demo). Bilinear
    sampling of the containing cell keeps the drift smooth and deterministic;
    nearest-node sampling would introduce step jumps that show up as spurious
    kinks in the hindcast path. Positions outside the grid are CLAMPED to the
    nearest edge and recorded as a warning - never silently extrapolated.

WHAT IT IS NOT
    Not an ocean model. The demo field is steady in time (documented in the
    file itself); windage is a prototype coefficient, not a calibrated value.
    Production work would ingest an operational model with proper advection
    (docs/methodology.md limitations section).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

if __package__ in (None, ""):  # executed directly as a script
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.geo import M_PER_DEG_LAT, metres_per_degree_lon
else:
    from app.geo import M_PER_DEG_LAT, metres_per_degree_lon

__all__ = ["EnvironmentalFieldError", "EnvironmentalField"]


class EnvironmentalFieldError(RuntimeError):
    """Raised when the environmental field is missing or structurally invalid."""


@dataclass
class EnvironmentalField:
    """A regular lat/lon grid of current and wind vectors plus a windage factor.

    Vector components are (u, v) in m/s, eastward/northward positive. The grid
    axes are sorted ascending; node (i, j) lives at (latitudes[i], longitudes[j])
    and is stored row-major so lookup is a flat index.
    """

    latitudes: List[float]
    longitudes: List[float]
    u_current: List[List[float]]   # [i_lat][i_lon]
    v_current: List[List[float]]
    u_wind: List[List[float]]
    v_wind: List[List[float]]
    windage: float
    provider: str = "unknown"
    synthetic: bool = False
    dataset_label: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    time_behaviour: Optional[str] = None
    units: Dict[str, str] = dataclass_field(default_factory=dict)
    notes: List[str] = dataclass_field(default_factory=list)
    warnings: List[str] = dataclass_field(default_factory=list)
    source_path: Optional[str] = None


    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, path: Path) -> "EnvironmentalField":
        """Load a field JSON file, failing loudly on structural problems."""
        path = Path(path)
        if not path.exists():
            raise EnvironmentalFieldError(
                f"environmental field not found at {path}; regenerate the demo bundle "
                "with python3 intelligence/data/demo/generate_case_001.py"
            )
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EnvironmentalFieldError(f"could not read environmental field {path}: {exc}") from exc

        grid = raw.get("grid") or {}
        nodes = raw.get("nodes")
        try:
            lats = [float(v) for v in grid["latitudes"]]
            lons = [float(v) for v in grid["longitudes"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise EnvironmentalFieldError(
                f"environmental field {path} must define grid.latitudes and grid.longitudes"
            ) from exc
        if len(lats) < 2 or len(lons) < 2:
            raise EnvironmentalFieldError(
                f"environmental field {path} grid must have at least 2x2 nodes, "
                f"got {len(lats)}x{len(lons)}"
            )
        if not isinstance(nodes, list) or len(nodes) != len(lats) * len(lons):
            actual = len(nodes) if isinstance(nodes, list) else "absent"
            raise EnvironmentalFieldError(
                f"environmental field {path} has {actual} nodes but the grid declares "
                f"{len(lats)}x{len(lons)} = {len(lats) * len(lons)}"
            )

        n_lon = len(lons)
        u_cur: List[List[float]] = [[0.0] * n_lon for _ in lats]
        v_cur: List[List[float]] = [[0.0] * n_lon for _ in lats]
        u_w: List[List[float]] = [[0.0] * n_lon for _ in lats]
        v_w: List[List[float]] = [[0.0] * n_lon for _ in lats]
        for index, node in enumerate(nodes):
            i, j = divmod(index, n_lon)
            try:
                u_cur[i][j] = float(node["uCurrent"])
                v_cur[i][j] = float(node["vCurrent"])
                u_w[i][j] = float(node["uWind"])
                v_w[i][j] = float(node["vWind"])
            except (KeyError, TypeError, ValueError) as exc:
                raise EnvironmentalFieldError(
                    f"environmental field {path} node {index} is missing a numeric "
                    "uCurrent/vCurrent/uWind/vWind component"
                ) from exc

        windage = float(raw.get("windageCoefficient", 0.0))
        if not (0.0 <= windage <= 1.0):
            raise EnvironmentalFieldError(
                f"environmental field {path} windageCoefficient must be in [0, 1], got {windage}"
            )

        notes: List[str] = []
        for key in ("windageNote", "fallback", "analyticDefinition"):
            block = raw.get(key)
            if isinstance(block, dict):
                note = block.get("note")
                if note:
                    notes.append(str(note))
            elif isinstance(block, str) and block.strip():
                notes.append(block.strip())

        return cls(
            latitudes=lats, longitudes=lons,
            u_current=u_cur, v_current=v_cur, u_wind=u_w, v_wind=v_w,
            windage=windage,
            provider=str(raw.get("provider", "unknown")),
            synthetic=bool(raw.get("synthetic", False)),
            dataset_label=raw.get("datasetLabel"),
            valid_from=raw.get("validFrom"), valid_to=raw.get("validTo"),
            time_behaviour=raw.get("timeBehaviour"),
            units=dict(raw.get("units") or {}),

            notes=notes,
            source_path=str(path),
        )

    # ----------------------------------------------------------------- sampling
    def _cell(self, lat: float, lon: float) -> Tuple[int, int, float, float]:
        """Containing-cell indices and fractional position for a query.

        Queries outside the grid axes are clamped into the edge cell and the
        clamping is recorded once per call in `warnings`, because a drift path
        silently extrapolated beyond the field would be an invented current.
        """
        def locate(value: float, axis: Sequence[float]) -> Tuple[int, float]:
            if value <= axis[0]:
                return 0, 0.0
            if value >= axis[-1]:
                return len(axis) - 2, 1.0
            lo, hi = 0, len(axis) - 1
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if axis[mid] <= value:
                    lo = mid
                else:
                    hi = mid
            span = axis[hi] - axis[lo]
            frac = 0.0 if span == 0 else (value - axis[lo]) / span
            return lo, frac

        inside = (self.latitudes[0] <= lat <= self.latitudes[-1]
                  and self.longitudes[0] <= lon <= self.longitudes[-1])
        i, fy = locate(lat, self.latitudes)
        j, fx = locate(lon, self.longitudes)
        if not inside:
            message = (
                f"sample position ({lat:.4f}, {lon:.4f}) lies outside the environmental grid "
                f"[{self.latitudes[0]}..{self.latitudes[-1]}, "
                f"{self.longitudes[0]}..{self.longitudes[-1]}]; clamped to the grid edge"
            )
            if message not in self.warnings:
                self.warnings.append(message)
        return i, j, fy, fx

    @staticmethod
    def _bilinear(grid: List[List[float]], i: int, j: int, fy: float, fx: float) -> float:
        f00 = grid[i][j]
        f01 = grid[i][j + 1]
        f10 = grid[i + 1][j]
        f11 = grid[i + 1][j + 1]
        return ((1 - fy) * ((1 - fx) * f00 + fx * f01)
                + fy * ((1 - fx) * f10 + fx * f11))

    def current(self, lat: float, lon: float) -> Tuple[float, float]:
        """Surface current (u, v) in m/s at a position (bilinear)."""
        i, j, fy, fx = self._cell(lat, lon)
        return (self._bilinear(self.u_current, i, j, fy, fx),
                self._bilinear(self.v_current, i, j, fy, fx))

    def wind(self, lat: float, lon: float) -> Tuple[float, float]:
        """Wind vector (u, v) in m/s at a position (bilinear)."""
        i, j, fy, fx = self._cell(lat, lon)
        return (self._bilinear(self.u_wind, i, j, fy, fx),
                self._bilinear(self.v_wind, i, j, fy, fx))

    def drift(self, lat: float, lon: float, windage: Optional[float] = None) -> Tuple[float, float]:
        """Surface drift velocity (u, v) in m/s = current + windage * wind.

        `windage` overrides the field's published coefficient (a sensitivity
        knob for the hindcast); None uses the field's own value.
        """
        cu, cv = self.current(lat, lon)
        wu, wv = self.wind(lat, lon)
        factor = self.windage if windage is None else float(windage)
        return (cu + factor * wu, cv + factor * wv)

    def drift_step(self, lat: float, lon: float, dt_seconds: float,
                   windage: Optional[float] = None) -> Tuple[float, float]:
        """Advance one position by dt along the drift velocity (flat-earth).

        `dt_seconds` may be NEGATIVE to integrate backwards - the hindcast uses
        exactly this property, so there is ONE drift definition for both
        directions (forward for validation, backward for attribution).
        """
        u, v = self.drift(lat, lon, windage=windage)
        new_lat = lat + (v * dt_seconds) / M_PER_DEG_LAT
        new_lon = lon + (u * dt_seconds) / metres_per_degree_lon(new_lat)
        return (new_lat, new_lon)

    def describe(self) -> Dict[str, Any]:
        """JSON-friendly summary (grid axes only - nodes stay in the file)."""
        return {
            "provider": self.provider,
            "synthetic": self.synthetic,
            "datasetLabel": self.dataset_label,
            "validFrom": self.valid_from,
            "validTo": self.valid_to,
            "timeBehaviour": self.time_behaviour,
            "windageCoefficient": self.windage,
            "grid": {
                "latMin": self.latitudes[0], "latMax": self.latitudes[-1],
                "lonMin": self.longitudes[0], "lonMax": self.longitudes[-1],
                "latStep": round(self.latitudes[1] - self.latitudes[0], 6),
                "lonStep": round(self.longitudes[1] - self.longitudes[0], 6),
                "nodeCount": len(self.latitudes) * len(self.longitudes),
            },
            "units": dict(self.units),
            "notes": list(self.notes),
            "sourcePath": self.source_path,
        }