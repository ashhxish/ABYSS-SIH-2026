"""ABYSS - satellite observation / oil-spill detection (Phase 12).

Public surface: config, errors, the demo provider, and the detection entry
point. See satellite.py for the honesty rules this module enforces.
"""
from __future__ import annotations

from app.detection.satellite import (
    LOOK_ALIKE_CLASSES,
    MODULE_VERSION,
    DetectionConfig,
    DemoSatelliteProvider,
    SatelliteError,
    assess_look_alikes,
    characterise_polygon,
    detect_slick,
    load_demo_slick,
    observe_case,
)

__all__ = [
    "LOOK_ALIKE_CLASSES",
    "MODULE_VERSION",
    "DetectionConfig",
    "DemoSatelliteProvider",
    "SatelliteError",
    "assess_look_alikes",
    "characterise_polygon",
    "detect_slick",
    "load_demo_slick",
    "observe_case",
]
