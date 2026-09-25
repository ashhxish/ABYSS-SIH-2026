"""ABYSS - Phase 19 source adapters.

Adapters load external or demonstration files into validated NormalizedBatch instances
without modifying or coupling to the forensic core.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .contracts import NormalizedBatch, Provenance
from .validation import normalize_batch


class SatelliteAdapter:
    """Adapter for satellite observation scenes / scenarios."""

    @staticmethod
    def load_json(
        path_or_dict: Union[str, Path, Dict[str, Any]],
        *,
        provenance: Optional[Provenance] = None,
    ) -> NormalizedBatch:
        """Load a satellite scenario JSON file or dict into a NormalizedBatch."""
        source_file = None
        if isinstance(path_or_dict, (str, Path)):
            path = Path(path_or_dict)
            source_file = str(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw = dict(path_or_dict)

        if provenance is None:
            provenance = Provenance.from_dict(
                raw.get("provenance") if isinstance(raw.get("provenance"), dict) else None,
                sourceType="satellite",
                sourceFile=source_file,
            )

        # Single scenario is normalized as a batch of 1 record
        return normalize_batch("satellite", [raw], provenance=provenance)


class AisAdapter:
    """Adapter for AIS position extracts (CSV or records)."""

    @staticmethod
    def load_csv(
        path: Union[str, Path],
        *,
        provenance: Optional[Provenance] = None,
    ) -> NormalizedBatch:
        """Load an AIS CSV file into a NormalizedBatch."""
        csv_path = Path(path)
        records: List[Dict[str, Any]] = []

        with open(csv_path, mode="r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Strip leading/trailing whitespaces from keys and values
                clean_row = {
                    (k.strip() if k else k): (v.strip() if isinstance(v, str) else v)
                    for k, v in row.items()
                }
                records.append(clean_row)

        if provenance is None:
            provenance = Provenance(
                sourceType="ais",
                sourceFile=str(csv_path),
                sourceName="AIS CSV",
            )

        return normalize_batch("ais", records, provenance=provenance)


class EnvironmentalAdapter:
    """Adapter for environmental field grids (JSON node arrays)."""

    @staticmethod
    def load_json(
        path_or_dict: Union[str, Path, Dict[str, Any]],
        *,
        provenance: Optional[Provenance] = None,
    ) -> NormalizedBatch:
        """Load an environmental field JSON into a NormalizedBatch of node samples."""
        source_file = None
        if isinstance(path_or_dict, (str, Path)):
            path = Path(path_or_dict)
            source_file = str(path)
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw = dict(path_or_dict)

        nodes = raw.get("nodes", [])
        timestamp = raw.get("validFrom") or raw.get("timestamp") or "2026-03-14T00:00:00Z"
        windage = raw.get("windageCoefficient")
        synthetic = bool(raw.get("synthetic", False))
        dataset_label = raw.get("datasetLabel")

        records: List[Dict[str, Any]] = []
        for node in nodes:
            rec = dict(node)
            rec.setdefault("timestamp", timestamp)
            if windage is not None and "windageCoefficient" not in rec:
                rec["windageCoefficient"] = windage
            if "synthetic" not in rec:
                rec["synthetic"] = synthetic
            if dataset_label and "datasetLabel" not in rec:
                rec["datasetLabel"] = dataset_label
            records.append(rec)

        if provenance is None:
            provenance = Provenance(
                sourceType="environmental",
                sourceFile=source_file,
                sourceName=raw.get("provider", "EnvironmentalProvider"),
                synthetic=synthetic,
                datasetLabel=dataset_label,
            )

        return normalize_batch("environmental", records, provenance=provenance)


# Convenience functions
def ingest_satellite_scenario(path: Union[str, Path]) -> NormalizedBatch:
    return SatelliteAdapter.load_json(path)


def ingest_ais_csv(path: Union[str, Path]) -> NormalizedBatch:
    return AisAdapter.load_csv(path)


def ingest_environmental_json(path: Union[str, Path]) -> NormalizedBatch:
    return EnvironmentalAdapter.load_json(path)
