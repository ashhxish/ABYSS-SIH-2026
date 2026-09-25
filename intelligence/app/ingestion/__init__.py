"""ABYSS - Phase 19 normalized data ingestion layer.

This package provides the boundary between external/raw data sources
and the ABYSS forensic core:

  * `contracts`: normalized dataclasses (SatelliteObservation, AisReport,
    EnvironmentalObservation, Provenance, NormalizedBatch).
  * `validation`: strict contract validators with reproducible issue audits
    (errors reject, warnings drop optional fields).
  * `adapters`: file and payload ingest adapters for satellite scenarios,
    AIS CSV position feeds, and environmental vector fields.
"""
from __future__ import annotations

from .adapters import (
    AisAdapter,
    EnvironmentalAdapter,
    SatelliteAdapter,
    ingest_ais_csv,
    ingest_environmental_json,
    ingest_satellite_scenario,
)
from .contracts import (
    CONTRACT_VERSION,
    SYNTHETIC_LABEL,
    AisReport,
    ContractError,
    EnvironmentalObservation,
    NormalizedBatch,
    Provenance,
    SatelliteObservation,
)
from .validation import (
    ERROR,
    WARNING,
    ValidationIssue,
    ValidationReport,
    normalize_batch,
    validate_ais_report,
    validate_environmental_observation,
    validate_satellite_observation,
)

__all__ = [
    # Contracts
    "CONTRACT_VERSION",
    "SYNTHETIC_LABEL",
    "ContractError",
    "Provenance",
    "SatelliteObservation",
    "AisReport",
    "EnvironmentalObservation",
    "NormalizedBatch",
    # Validation
    "ERROR",
    "WARNING",
    "ValidationIssue",
    "ValidationReport",
    "validate_satellite_observation",
    "validate_ais_report",
    "validate_environmental_observation",
    "normalize_batch",
    # Adapters
    "SatelliteAdapter",
    "AisAdapter",
    "EnvironmentalAdapter",
    "ingest_satellite_scenario",
    "ingest_ais_csv",
    "ingest_environmental_json",
]
