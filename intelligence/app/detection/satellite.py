"""ABYSS - satellite observation / oil-spill detection (Phase 12).

PURPOSE
    First link of the evidence chain: turn a SAR-scene scenario asset into an
    observed, characterised **possible** oil slick with an explicit detection
    confidence and an honest look-alike assessment (docs/methodology.md s.3).

HONESTY RULES - this module enforces them, tests assert them
    * A dark formation in SAR imagery is NOT automatically oil. The result
      states which look-alike classes were assessed and which were not.
    * detectionConfidence is a prototype number for a synthetic scene. It is
      not a validated detection probability; the note travels with the value.
    * Demo mode reads a bundled PRE-COMPUTED polygon - no imagery processing
      runs at analysis time, so results are reproducible without API keys.
    * Synthetic labels (datasetLabel / uiLabel) propagate to every output.
    * The scenario answer key (demo_origin_expected.json) is never read here.

LOOK-ALIKE CLASSES CONSIDERED (methodology s.3)
    low wind area - natural or biogenic film - radar artefact - sea-state
    variation. Only the low-wind class can be checked in demo mode (wind at the
    slick centroid from the environmental field); the others are reported as
    NOT assessed rather than silently assumed absent.

CLI ACCESS
    The observation stage runs inside the investigation pipeline:
        cd intelligence && ../.venv/bin/python -m app.investigation
    and is unit-tested directly (tests/test_satellite_detection.py).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.geo import EARTH_RADIUS_KM, haversine_km, polygon_area_km2

MODULE_VERSION = "1.0.0"
DEMO_SLICK_FILENAME = "demo_slick.json"

LOOK_ALIKE_CLASSES = (
    "low wind area",
    "natural or biogenic film",
    "radar artefact",
    "sea-state variation",
)

DEFAULT_CONFIDENCE_NOTE = (
    "Prototype confidence attached to a synthetic demonstration scene. It is "
    "NOT a scientifically validated detection probability and does not "
    "constitute ground truth."
)

OTHER_CLASSES_NOTE = (
    "Natural/biogenic films, radar artefacts and sea-state variations cannot "
    "be excluded from a single synthetic scene: they are reported as NOT "
    "assessed. A real investigation needs multi-sensor or in-situ confirmation."
)

PROVENANCE = "pre-computed polygon (demo mode): no imagery processing at run time"


class SatelliteError(RuntimeError):
    """Raised when a satellite scenario asset is missing or malformed."""


@dataclass(frozen=True)
class DetectionConfig:
    """Prototype thresholds. Reported back with every result - not constants."""

    low_wind_threshold_ms: float = 3.0
    min_confidence: float = 0.5

    def __post_init__(self) -> None:
        if self.low_wind_threshold_ms < 0.0:
            raise ValueError("low_wind_threshold_ms must be >= 0")
        if not (0.0 < self.min_confidence <= 1.0):
            raise ValueError("min_confidence must be in (0, 1]")

    def to_dict(self) -> Dict[str, float]:
        return {
            "lowWindThresholdMs": self.low_wind_threshold_ms,
            "minConfidence": self.min_confidence,
        }


# --------------------------------------------------------------------------
# Scenario asset loading (demo provider)
# --------------------------------------------------------------------------

def _read_scenario(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise SatelliteError(f"satellite scenario not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SatelliteError(f"satellite scenario unreadable: {path}: {exc}") from exc
    if not isinstance(data, dict) or "geometry" not in data:
        raise SatelliteError(f"satellite scenario malformed (no geometry): {path}")
    confidence = data.get("detectionConfidence")
    if not isinstance(confidence, (int, float)) or not (0.0 < float(confidence) <= 1.0):
        raise SatelliteError(f"satellite scenario has no usable detectionConfidence: {path}")
    if not data.get("acquisitionTime"):
        raise SatelliteError(f"satellite scenario has no acquisitionTime: {path}")
    return data


def load_demo_slick(case_dir: Path) -> Dict[str, Any]:
    """Load and validate the bundled demo slick scenario for one case directory."""
    return _read_scenario(Path(case_dir) / DEMO_SLICK_FILENAME)


class DemoSatelliteProvider:
    """Satellite data provider for DEMO MODE (docs/architecture.md s.23).

    Returns a bundled, pre-computed slick polygon. It needs no API keys, makes
    no network calls, and is deterministic - which is exactly what a hackathon
    demonstration requires. A live provider would implement the same fetch()
    contract behind the same interface later.
    """

    name = "DemoSatelliteProvider"

    def __init__(self, scenario_path: Path) -> None:
        self.scenario_path = Path(scenario_path)

    @classmethod
    def for_case(cls, case_dir: Path) -> "DemoSatelliteProvider":
        return cls(Path(case_dir) / DEMO_SLICK_FILENAME)

    @property
    def label(self) -> str:
        return f"{self.name} ({self.scenario_path.name}: {PROVENANCE})"

    def fetch(self) -> Dict[str, Any]:
        """Return the validated scenario mapping (raises SatelliteError)."""
        return _read_scenario(self.scenario_path)


# --------------------------------------------------------------------------
# Polygon extraction & characterisation (docs/methodology.md s.3)
# --------------------------------------------------------------------------

def _extract_ring(geometry: Dict[str, Any]) -> List[Tuple[float, float]]:
    """Extract a closed outer [(lon, lat), ...] ring from GeoJSON geometry.

    Supports Polygon and MultiPolygon (first ring of the first polygon).
    Raises SatelliteError if the geometry is invalid, non-polygonal or degenerate.
    """
    if not isinstance(geometry, dict):
        raise SatelliteError(f"geometry must be a dict, got {type(geometry).__name__}")
    g_type = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords or not isinstance(coords, list):
        raise SatelliteError("geometry coordinates must be a non-empty list")

    if g_type == "Polygon":
        ring = coords[0]
    elif g_type == "MultiPolygon":
        if not coords[0] or not isinstance(coords[0], list):
            raise SatelliteError("MultiPolygon has empty outer polygon")
        ring = coords[0][0]
    else:
        raise SatelliteError(f"unsupported geometry type: {g_type!r}; expected Polygon/MultiPolygon")

    if not isinstance(ring, list) or len(ring) < 4:
        raise SatelliteError(f"slick ring must contain at least 4 coordinates, got {len(ring) if isinstance(ring, list) else 'non-list'}")

    try:
        pts = [(float(p[0]), float(p[1])) for p in ring]
    except (IndexError, TypeError, ValueError) as exc:
        raise SatelliteError(f"invalid coordinate pair in ring: {exc}") from exc

    return pts


def characterise_polygon(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Characterise a slick polygon: area, centroid, bounding box, perimeter.

    Takes a scenario dict containing at least `geometry`. Computes geometric
    metrics using shared geodesy helpers, and retains pre-computed elliptical
    metrics (length, width, orientation) when supplied by the scenario asset.
    """
    geometry = scenario.get("geometry")
    if not geometry:
        raise SatelliteError("scenario has no geometry to characterise")
    ring = _extract_ring(geometry)

    open_ring = ring[:-1] if ring and ring[0] == ring[-1] else ring
    if len(open_ring) < 3:
        raise SatelliteError("slick ring has fewer than 3 distinct vertices")

    area_km2 = polygon_area_km2(ring)

    mean_lon = sum(p[0] for p in open_ring) / len(open_ring)
    mean_lat = sum(p[1] for p in open_ring) / len(open_ring)

    lats = [p[1] for p in open_ring]
    lons = [p[0] for p in open_ring]
    bbox = {
        "minLat": round(min(lats), 6),
        "maxLat": round(max(lats), 6),
        "minLon": round(min(lons), 6),
        "maxLon": round(max(lons), 6),
    }

    perimeter_km = 0.0
    for i in range(len(ring) - 1):
        perimeter_km += haversine_km(ring[i][1], ring[i][0], ring[i + 1][1], ring[i + 1][0])

    result: Dict[str, Any] = {
        "geometry": geometry,
        "vertexCount": len(ring),
        "areaKm2": round(area_km2, 3),
        "centroid": {"lat": round(mean_lat, 6), "lon": round(mean_lon, 6)},
        "boundingBox": bbox,
        "perimeterKm": round(perimeter_km, 3),
    }

    for key in ("approximateLengthKm", "approximateWidthKm", "orientationDeg", "orientationNote"):
        if key in scenario:
            result[key] = scenario[key]

    return result


# --------------------------------------------------------------------------
# Look-alike assessment (docs/methodology.md s.3)
# --------------------------------------------------------------------------

def assess_look_alikes(
    centroid: Dict[str, float],
    field: Optional[Any] = None,
    config: Optional[DetectionConfig] = None,
    scenario_assessment: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assess look-alike dark SAR formations.

    Honesty rules:
      * Only low-wind area can be assessed at runtime if an EnvironmentalField is available.
      * Natural films, radar artefacts, and sea-state variations are reported as NOT assessed.
    """
    cfg = config or DetectionConfig()
    lat = float(centroid.get("lat", 0.0))
    lon = float(centroid.get("lon", 0.0))

    low_wind_suspected: Optional[bool] = None
    wind_speed_ms: Optional[float] = None
    checked_classes: List[str] = []
    not_assessed = [c for c in LOOK_ALIKE_CLASSES if c != "low wind area"]
    notes: List[str] = [OTHER_CLASSES_NOTE]

    if field is not None and hasattr(field, "wind"):
        try:
            wu, wv = field.wind(lat, lon)
            speed = math.hypot(wu, wv)
            wind_speed_ms = round(speed, 2)
            low_wind_suspected = speed < cfg.low_wind_threshold_ms
            checked_classes.append("low wind area")
            if low_wind_suspected:
                notes.append(
                    f"Low wind speed ({wind_speed_ms:.1f} m/s < {cfg.low_wind_threshold_ms:.1f} m/s) "
                    "at slick centroid: formation could be a low-wind surface calm."
                )
            else:
                notes.append(
                    f"Wind speed at slick centroid ({wind_speed_ms:.1f} m/s >= {cfg.low_wind_threshold_ms:.1f} m/s) "
                    "argues against a low-wind calm look-alike."
                )
        except Exception as exc:
            notes.append(f"Wind lookup at centroid failed ({exc}); low wind not verified.")
    else:
        notes.append("Environmental field not supplied: low-wind check could not be run.")

    scenario_warn = bool(scenario_assessment.get("lookAlikeWarning", False)) if scenario_assessment else False
    look_alike_warning = bool(low_wind_suspected) or scenario_warn

    return {
        "classesConsidered": list(LOOK_ALIKE_CLASSES),
        "checkedClasses": checked_classes,
        "notAssessedClasses": not_assessed,
        "lowWindArea": low_wind_suspected,
        "windSpeedMs": wind_speed_ms,
        "thresholdMs": cfg.low_wind_threshold_ms,
        "lookAlikeWarning": look_alike_warning,
        "notes": notes,
    }


# --------------------------------------------------------------------------
# Slick detection and observation entry points
# --------------------------------------------------------------------------

def detect_slick(
    scenario: Dict[str, Any],
    field: Optional[Any] = None,
    config: Optional[DetectionConfig] = None,
) -> Dict[str, Any]:
    """Detect and characterise a possible slick from a scenario asset.

    Enforces prototype honesty: detectionConfidence travels with its disclaimer note,
    look-alike classes are explicitly enumerated, and synthetic labels travel.
    """
    cfg = config or DetectionConfig()
    char = characterise_polygon(scenario)
    look_alikes = assess_look_alikes(
        char["centroid"],
        field=field,
        config=cfg,
        scenario_assessment=scenario.get("lookAlikeAssessment"),
    )

    conf = float(scenario.get("detectionConfidence", 0.0))
    conf_note = scenario.get("detectionConfidenceNote", DEFAULT_CONFIDENCE_NOTE)

    warnings: List[str] = []
    if scenario.get("synthetic", True):
        warnings.append("synthetic demonstration data (DEMO DATA) - not a real satellite acquisition")
    if look_alikes["lookAlikeWarning"]:
        warnings.append("look-alike warning: dark formation characteristics are ambiguous")
    if conf < cfg.min_confidence:
        warnings.append(f"detection confidence {conf:.2f} is below prototype threshold {cfg.min_confidence:.2f}")

    return {
        "module": "detection",
        "moduleVersion": MODULE_VERSION,
        "synthetic": bool(scenario.get("synthetic", True)),
        "datasetLabel": scenario.get("datasetLabel", "Synthetic Demonstration Dataset"),
        "uiLabel": scenario.get("uiLabel", "DEMO DATA"),
        "caseId": scenario.get("caseId"),
        "spillId": scenario.get("spillId"),
        "acquisitionTime": scenario.get("acquisitionTime"),
        "sensor": scenario.get("sensor", {}),
        "detected": True,
        "classification": "possible oil slick (dark formation candidate)",
        "detectionConfidence": conf,
        "detectionConfidenceNote": conf_note,
        "meetsConfidenceThreshold": conf >= cfg.min_confidence,
        "characterisation": char,
        "lookAlikeWarning": look_alikes["lookAlikeWarning"],
        "lookAlikeAssessment": look_alikes,
        "geometry": char["geometry"],
        "provenance": scenario.get("provenance", PROVENANCE),
        "config": cfg.to_dict(),
        "warnings": warnings,
    }


def observe_case(
    case_dir: Path,
    field: Optional[Any] = None,
    config: Optional[DetectionConfig] = None,
    provider: Optional[DemoSatelliteProvider] = None,
) -> Dict[str, Any]:
    """Run Phase 12 satellite observation stage for a case directory."""
    case_path = Path(case_dir)
    sat_provider = provider or DemoSatelliteProvider.for_case(case_path)
    scenario = sat_provider.fetch()

    if field is None:
        try:
            from app.hindcast.environmental import EnvironmentalField
            env_path = case_path / "environmental" / "demo_environmental_field.json"
            if env_path.is_file():
                field = EnvironmentalField.load(env_path)
        except Exception:
            field = None

    detection = detect_slick(scenario, field=field, config=config)
    detection["dataSource"] = sat_provider.label
    return detection

