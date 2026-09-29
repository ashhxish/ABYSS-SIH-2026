"""ABYSS - real Sentinel-1 SAR / U-Net oil-spill adapter (Phase 1).

PIPELINE
    Real Sentinel-1 GeoTIFF (VV + VH)
      -> validate raster (2 float bands, finite values)
      -> 256x256 non-overlapping patches (teammate behaviour: edge pixels
         NOT divisible by 256 are excluded, never padded or stretched)
      -> per-channel patch normalisation ((x - mean) / (std + 1e-8))
      -> actual U-Net inference (``best_unet_oil_spill.pth`` via
         ``ABYSS_SENTINEL1_MODEL_PATH``) + sigmoid
      -> threshold 0.5 -> full-resolution binary mask
      -> connected-component labelling (8-connectivity, scipy)
      -> polygonize each kept region with the SOURCE raster transform
         (rasterio.features.shapes: pixel-exact, no resampling)
      -> geodesic area in km^2 (pyproj.Geod on WGS84 when the source CRS is
         geographic; source-CRS planar area otherwise)
      -> :class:`app.ingestion.contracts.SatelliteObservation`

HONESTY RULES (Phase 1 constraints, enforced here and asserted by tests)
    * The checkpoint is resolved ONLY through ``ABYSS_SENTINEL1_MODEL_PATH``.
      No absolute user path is hard-coded into this module.
    * A missing checkpoint raises :class:`Sentinel1Error` with a useful
      message. A requested REAL inference NEVER silently falls back to the
      synthetic CASE-001 scene.
    * The U-Net emits a binary mask. The binary mask is NOT a calibrated
      detection probability, so ``detectionConfidence`` is left ``None``
      (unknown) instead of fabricating a confidence number.
    * ``processed_at``-style metadata is NEVER used as the acquisition time.
      The supplied 00999.tif carries no acquisition timestamp, so
      ``acquisitionTime`` is ``None`` with an explicit provenance warning.
    * All regions are kept (``MIN_REGION_PIXELS = 1``): disconnected spill
      parts are never silently discarded. Regions are ordered
      deterministically by pixel count (descending), then by bounding box.
    * Longitude/latitude order follows GeoJSON ([lon, lat]) everywhere, and
      the existing :class:`SatelliteObservation` contract is reused unchanged.

The synthetic CASE-001 path (``satellite.py`` demo provider) is untouched.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.ingestion.contracts import Provenance, SatelliteObservation

MODULE_VERSION = "1.0.0"
MODEL_ENV_VAR = "ABYSS_SENTINEL1_MODEL_PATH"
PATCH_SIZE = 256
THRESHOLD = 0.5
# Keep every detected region: nothing detected is silently discarded.
MIN_REGION_PIXELS = 1
MODEL_NAME = "best_unet_oil_spill.pth"
_EPS = 1e-8


class Sentinel1Error(RuntimeError):
    """Raised when a real Sentinel-1 inference cannot be performed honestly."""


# ---------------------------------------------------------------------------
# Model configuration (Step 3)
# ---------------------------------------------------------------------------

def resolve_model_path(explicit: Optional[str] = None) -> Path:
    """Resolve the U-Net checkpoint path.

    Precedence: explicit argument, then ``ABYSS_SENTINEL1_MODEL_PATH``.
    Raises :class:`Sentinel1Error` with a useful message when the checkpoint
    does not exist - callers must NOT fall back to synthetic data.
    """
    raw = explicit if explicit not in (None, "") else os.environ.get(MODEL_ENV_VAR, "")
    candidate = str(raw).strip()
    if not candidate:
        raise Sentinel1Error(
            "real Sentinel-1 inference requested but no checkpoint configured: "
            f"set {MODEL_ENV_VAR} to the path of {MODEL_NAME} "
            "(dev checkpoint lives outside the repo and is never committed to git)"
        )
    path = Path(candidate).expanduser()
    if not path.is_file():
        raise Sentinel1Error(
            f"Sentinel-1 U-Net checkpoint not found at {path} "
            f"(configured via {'argument' if explicit not in (None, '') else MODEL_ENV_VAR}); "
            "refusing to fall back to synthetic data for a real inference"
        )
    return path


def load_unet(checkpoint_path: Path):
    """Load the teammate's actual U-Net weights (eval mode, CPU or CUDA)."""
    import torch  # local import: torch is an optional Phase 1 dependency

    from app.detection.unet import UNet

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = UNet(in_channels=2, out_channels=1)
    checkpoint = torch.load(str(checkpoint_path), map_location=device)
    state = checkpoint.get("model_state_dict", checkpoint)
    model.load_state_dict(state)
    model.to(device)
    model.eval()
    return model, device


def checkpoint_sha256(path: Path) -> str:
    """Short content hash of the checkpoint for provenance (streamed)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

# ---------------------------------------------------------------------------
# Raster validation + patching (teammate behaviour, Steps 2/4/5)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RasterInfo:
    """Source-raster facts every later stage must reuse (never recompute)."""

    path: str
    width: int
    height: int
    count: int
    crs: str
    transform: Tuple[float, float, float, float, float, float]
    bounds: Tuple[float, float, float, float]  # left, bottom, right, top
    dtypes: Tuple[str, ...]
    tags: Dict[str, str]


def read_sentinel1(path: Path):
    """Open a Sentinel-1 GeoTIFF and validate the VV/VH contract.

    Returns ``(image, info)`` where ``image`` is float32 ``(2, H, W)``.
    Raises :class:`Sentinel1Error` for missing files, band-count mismatch,
    non-finite values, or degenerate dimensions.
    """
    import rasterio  # local import: rasterio is an optional Phase 1 dependency

    tiff = Path(path)
    if not tiff.is_file():
        raise Sentinel1Error(f"Sentinel-1 scene not found at {tiff}")
    with rasterio.open(str(tiff)) as src:
        if src.count != 2:
            raise Sentinel1Error(
                f"expected 2 bands (VV + VH) in {tiff}, found {src.count}"
            )
        if src.width <= 0 or src.height <= 0:
            raise Sentinel1Error(
                f"degenerate raster dimensions in {tiff}: {src.width}x{src.height}"
            )
        image = src.read().astype(np.float32)
        info = RasterInfo(
            path=str(tiff),
            width=int(src.width),
            height=int(src.height),
            count=int(src.count),
            crs=str(src.crs) if src.crs else "",
            transform=tuple(float(v) for v in tuple(src.transform)),
            bounds=(float(src.bounds.left), float(src.bounds.bottom),
                    float(src.bounds.right), float(src.bounds.top)),
            dtypes=tuple(str(d) for d in src.dtypes),
            tags={str(k): str(v) for k, v in src.tags().items()},
        )
    if not np.all(np.isfinite(image)):
        raise Sentinel1Error(
            f"non-finite (NaN/inf) backscatter values in {tiff}; "
            "refusing to normalise non-finite input"
        )
    return image, info


def normalize_patch(patch: np.ndarray) -> np.ndarray:
    """Per-channel patch normalisation: ``(x - mean) / (std + 1e-8)``.

    Exact teammate behaviour from ``sentinel1_integration/inference.py``.
    """
    normed = patch.copy()
    for c in range(normed.shape[0]):
        mean = float(normed[c].mean())
        std = float(normed[c].std())
        normed[c] = (normed[c] - mean) / (std + _EPS)
    return normed


def create_patches(image: np.ndarray,
                   patch_size: int = PATCH_SIZE) -> Tuple[List[np.ndarray], List[Tuple[int, int]]]:
    """Tile ``(C, H, W)`` into non-overlapping ``patch_size`` squares.

    Teammate behaviour: only full patches are taken (``range(0, dim - size +
    1, size)``); edge pixels that do not fill a patch are excluded, never
    padded. Positions are ``(row, col)`` top-left pixel indices.
    """
    _, height, width = image.shape
    patches: List[np.ndarray] = []
    positions: List[Tuple[int, int]] = []
    for y in range(0, height - patch_size + 1, patch_size):
        for x in range(0, width - patch_size + 1, patch_size):
            patches.append(image[:, y:y + patch_size, x:x + patch_size])
            positions.append((y, x))
    return patches, positions


# ---------------------------------------------------------------------------
# Inference (actual U-Net, Step 2/4)
# ---------------------------------------------------------------------------

def run_inference(image: np.ndarray, model, device,
                  patch_size: int = PATCH_SIZE,
                  threshold: float = THRESHOLD) -> Tuple[np.ndarray, np.ndarray]:
    """Run the U-Net over all patches; return ``(probability, mask)``.

    ``probability`` is the sigmoid output at full resolution (float32
    ``(H, W)``); ``mask`` is the ``threshold``-binarised uint8 ``(H, W)``.
    Pixels outside the patch grid (image dims not divisible by 256) stay 0.
    """
    import torch  # local import: torch is an optional Phase 1 dependency

    _, height, width = image.shape
    probability = np.zeros((height, width), dtype=np.float32)
    patches, positions = create_patches(image, patch_size)
    if not patches:
        raise Sentinel1Error(
            f"image {width}x{height} is smaller than PATCH_SIZE {patch_size}; "
            "no inference patches can be formed"
        )
    with torch.no_grad():
        for patch, (y, x) in zip(patches, positions):
            tensor = torch.from_numpy(normalize_patch(patch)).unsqueeze(0).to(device)
            logits = model(tensor)
            prob = torch.sigmoid(logits).cpu().numpy()[0, 0]
            probability[y:y + patch_size, x:x + patch_size] = prob.astype(np.float32)
    mask = (probability >= float(threshold)).astype(np.uint8)
    return probability, mask

# ---------------------------------------------------------------------------
# Geospatial processing (Step 5)
# ---------------------------------------------------------------------------

@dataclass
class SpillRegion:
    """One connected mask component with pixel-exact vector geometry."""

    label_id: int
    pixels: int
    row_min: int
    row_max: int
    col_min: int
    col_max: int
    geometry: Dict[str, Any]          # GeoJSON Polygon in source CRS coords
    area_km2: float
    centroid_lon: float
    centroid_lat: float
    bbox: Tuple[float, float, float, float]  # minLon, minLat, maxLon, maxLat

    def to_dict(self) -> Dict[str, Any]:
        return {
            "labelId": self.label_id,
            "pixels": self.pixels,
            "rowRange": [self.row_min, self.row_max],
            "colRange": [self.col_min, self.col_max],
            "geometry": self.geometry,
            "areaKm2": self.area_km2,
            "centroid": {"lon": self.centroid_lon, "lat": self.centroid_lat},
            "bbox": list(self.bbox),
        }


def _geod():
    from pyproj import Geod  # local import: pyproj is an optional Phase 1 dependency
    return Geod(ellps="WGS84")


def geodesic_area_km2(lons: List[float], lats: List[float]) -> float:
    """Ellipsoidal polygon area in km^2 (correct for EPSG:4326 source data)."""
    if len(lons) < 3:
        return 0.0
    area_m2, _ = _geod().polygon_area_perimeter(list(lons), list(lats))
    return abs(area_m2) / 1e6


def planar_area_km2(flat_ring: List[Tuple[float, float]], linear_unit_m: float = 1.0) -> float:
    """Shoelace area for projected CRS data (units scaled to metres first)."""
    pts = [(float(x) * linear_unit_m, float(y) * linear_unit_m) for x, y in flat_ring]
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return 0.0
    total = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0 / 1e6


def label_regions(mask: np.ndarray,
                  min_pixels: int = MIN_REGION_PIXELS) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """8-connected component labelling, deterministic order (size desc, bbox).

    Returns ``(label_image, descriptors)``; every component with at least
    ``min_pixels`` pixels is kept (default 1: nothing is silently dropped).
    """
    from scipy import ndimage  # local import: scipy is an optional Phase 1 dependency

    binary = mask > 0
    structure = np.ones((3, 3), dtype=np.uint8)
    labelled, n_regions = ndimage.label(binary, structure=structure)
    descriptors: List[Dict[str, Any]] = []
    for region_id in range(1, n_regions + 1):
        rows, cols = np.where(labelled == region_id)
        pixels = int(rows.size)
        if pixels < min_pixels:
            continue
        descriptors.append({
            "label_id": int(region_id),
            "pixels": pixels,
            "row_min": int(rows.min()),
            "row_max": int(rows.max()),
            "col_min": int(cols.min()),
            "col_max": int(cols.max()),
        })
    # Deterministic handling: largest first, ties broken by bounding box.
    descriptors.sort(key=lambda d: (-d["pixels"], d["row_min"], d["col_min"],
                                    d["row_max"], d["col_max"]))
    return labelled, descriptors


def is_geographic_crs(crs_text: str) -> bool:
    """True for EPSG:4326-style geographic CRS (degrees, needs geodesic area)."""
    text = (crs_text or "").upper()
    return "4326" in text or "WGS 84" in text or "WGS84" in text


def polygonize_regions(labelled: np.ndarray,
                       descriptors: List[Dict[str, Any]],
                       info: RasterInfo) -> List[SpillRegion]:
    """Vectorise each labelled region with the SOURCE raster transform.

    Uses ``rasterio.features.shapes`` on a per-region binary image, so
    polygons are pixel-exact in source CRS coordinates (no resampling, no
    axis swap: rasterio yields ``(x, y)`` = ``(lon, lat)`` for EPSG:4326).
    The largest-area polygon of a region becomes its geometry; area uses the
    geodesic (WGS84) for geographic CRS, else source-unit planar maths.
    """
    import rasterio.features as rfeatures  # local import (optional Phase 1 dep)
    from rasterio.transform import Affine

    transform = Affine(*info.transform)
    geographic = is_geographic_crs(info.crs)
    regions: List[SpillRegion] = []
    for order, desc in enumerate(descriptors, start=1):
        binary = (labelled == desc["label_id"]).astype(np.uint8)
        best_poly = None
        best_area = -1.0
        for geom, value in rfeatures.shapes(binary, transform=transform):
            if int(value) != 1:
                continue
            rings = []
            if geom["type"] == "Polygon":
                rings = [geom["coordinates"][0]]
            elif geom["type"] == "MultiPolygon":
                rings = [poly[0] for poly in geom["coordinates"]]
            else:
                continue
            for ring in rings:
                xs = [float(p[0]) for p in ring]
                ys = [float(p[1]) for p in ring]
                area = (geodesic_area_km2(xs, ys) if geographic
                        else planar_area_km2(list(zip(xs, ys))))
                if area > best_area:
                    best_area = area
                    best_poly = [[float(p[0]), float(p[1])] for p in ring]
        if best_poly is None:
            continue
        xs = [p[0] for p in best_poly]
        ys = [p[1] for p in best_poly]
        regions.append(SpillRegion(
            label_id=order,
            pixels=desc["pixels"],
            row_min=desc["row_min"],
            row_max=desc["row_max"],
            col_min=desc["col_min"],
            col_max=desc["col_max"],
            geometry={"type": "Polygon", "coordinates": [best_poly]},
            area_km2=float(best_area),
            centroid_lon=float(sum(xs) / len(xs)),
            centroid_lat=float(sum(ys) / len(ys)),
            bbox=(float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))),
        ))
    return regions


def combine_geometry(regions: List[SpillRegion]) -> Optional[Dict[str, Any]]:
    """Deterministic MultiPolygon/Polygon over all kept regions (or None)."""
    if not regions:
        return None
    polys = [r.geometry["coordinates"] for r in regions]
    if len(polys) == 1:
        return {"type": "Polygon", "coordinates": polys[0]}
    return {"type": "MultiPolygon",
            "coordinates": [[ring for ring in poly] for poly in polys]}

# ---------------------------------------------------------------------------
# End-to-end result + SatelliteObservation conversion (Step 6)
# ---------------------------------------------------------------------------

@dataclass
class Sentinel1Result:
    """Everything the real-data path produces for one scene."""

    scene_path: str
    info: RasterInfo
    probability: np.ndarray = field(repr=False)
    mask: np.ndarray = field(repr=False)
    oil_pixels: int = 0
    oil_fraction: float = 0.0
    regions: List[SpillRegion] = field(default_factory=list)
    geometry: Optional[Dict[str, Any]] = None
    centroid: Dict[str, float] = field(default_factory=dict)
    bbox: List[float] = field(default_factory=list)
    area_km2: float = 0.0
    model_path: str = ""
    model_sha256: str = ""
    inference_timestamp: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenePath": self.scene_path,
            "width": self.info.width,
            "height": self.info.height,
            "crs": self.info.crs,
            "bounds": list(self.info.bounds),
            "oilPixels": self.oil_pixels,
            "oilFraction": self.oil_fraction,
            "regionCount": len(self.regions),
            "regions": [r.to_dict() for r in self.regions],
            "geometry": self.geometry,
            "centroid": self.centroid,
            "bbox": self.bbox,
            "areaKm2": self.area_km2,
            "modelPath": self.model_path,
            "modelSha256": self.model_sha256,
            "inferenceTimestamp": self.inference_timestamp,
            "warnings": list(self.warnings),
        }


def detect_scene(scene_path: Path,
                 model_path: Optional[str] = None) -> Sentinel1Result:
    """Run the full real-data chain: TIFF -> U-Net -> mask -> geometry."""
    image, info = read_sentinel1(Path(scene_path))
    ckpt = resolve_model_path(model_path)
    model, device = load_unet(ckpt)
    probability, mask = run_inference(image, model, device)
    labelled, descriptors = label_regions(mask)
    regions = polygonize_regions(labelled, descriptors, info)
    geometry = combine_geometry(regions)

    oil_pixels = int(mask.sum())
    oil_fraction = float(oil_pixels / mask.size) if mask.size else 0.0
    area_km2 = float(sum(r.area_km2 for r in regions))
    if regions:
        total_px = max(sum(r.pixels for r in regions), 1)
        centroid = {"lat": float(sum(r.centroid_lat * r.pixels for r in regions) / total_px),
                    "lon": float(sum(r.centroid_lon * r.pixels for r in regions) / total_px)}
        bbox = [min(r.bbox[0] for r in regions), min(r.bbox[1] for r in regions),
                max(r.bbox[2] for r in regions), max(r.bbox[3] for r in regions)]
    else:
        centroid, bbox = {}, []

    warnings: List[str] = []
    if oil_pixels == 0:
        warnings.append("U-Net mask is empty: no oil pixels at threshold 0.5; "
                        "no spill geometry produced")
    dropped = int((mask > 0).sum()) - sum(r.pixels for r in regions)
    if dropped:
        warnings.append(f"{dropped} oil pixels not represented by region polygons")
    return Sentinel1Result(
        scene_path=str(scene_path),
        info=info,
        probability=probability,
        mask=mask,
        oil_pixels=oil_pixels,
        oil_fraction=oil_fraction,
        regions=regions,
        geometry=geometry,
        centroid=centroid,
        bbox=bbox,
        area_km2=area_km2,
        model_path=str(ckpt),
        model_sha256=checkpoint_sha256(ckpt),
        inference_timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        warnings=warnings,
    )


def to_satellite_observation(result: Sentinel1Result,
                             case_id: str = "CASE-REAL-001") -> SatelliteObservation:
    """Convert a real Sentinel-1 result into the EXISTING contract (Step 6).

    ``detectionConfidence`` stays ``None``: a binary mask is not a calibrated
    probability and this adapter will not fabricate one. ``acquisitionTime``
    stays ``None`` with an explicit provenance warning because the supplied
    sample carries no trustworthy acquisition timestamp (and ``processed_at``
    is NOT an acquisition time).
    """
    provenance = Provenance(
        sourceType="satellite",
        sourceName="Sentinel-1 SAR (VV+VH)",
        sourceFile=result.scene_path,
        originalId=Path(result.scene_path).name,
        synthetic=False,
        datasetLabel="Real Sentinel-1 acquisition (U-Net segmentation)",
    )
    geometry = result.geometry or {"type": "Polygon", "coordinates": []}
    return SatelliteObservation(
        acquisitionTime=None,
        geometry=geometry,
        centroid=dict(result.centroid),
        sensor={"platform": "Sentinel-1", "mode": "SAR",
                "bands": ["VV", "VH"], "instrument": "C-SAR"},
        detectionConfidence=None,
        detectionConfidenceNote=(
            "Real U-Net segmentation: the model emits a binary mask, not a "
            "calibrated detection probability. No confidence number is reported."
        ),
        lookAlikeWarning=None,
        lookAlikeAssessment={"assessed": False,
                             "note": "look-alike screening not run in Phase 1"},
        caseId=case_id,
        spillId=None,
        characteristics={
            "areaKm2": result.area_km2,
            "oilPixels": result.oil_pixels,
            "oilFraction": result.oil_fraction,
            "regionCount": len(result.regions),
            "sceneWidth": result.info.width,
            "sceneHeight": result.info.height,
            "crs": result.info.crs,
            "sceneBounds": list(result.info.bounds),
            "modelName": MODEL_NAME,
            "modelSha256": result.model_sha256,
            "patchSize": PATCH_SIZE,
            "threshold": THRESHOLD,
            "preprocessing": ("per-channel patch normalisation (x-mean)/(std+1e-8), "
                              "256x256 non-overlapping patches, edge pixels excluded"),
            "inferenceTimestamp": result.inference_timestamp,
        },
        provenance=provenance,
    )


def result_warnings(result: Sentinel1Result) -> List[str]:
    """Provenance warnings for a real Sentinel-1 result (incl. Step 6 rule)."""
    out = [
        "acquisition time unknown: the supplied Sentinel-1 sample carries no "
        "trustworthy acquisition timestamp (processed_at is NOT an acquisition "
        "time), so acquisitionTime is null",
    ]
    out.extend(result.warnings)
    return out


def generate_preview_layers(scene_path: str, mask: np.ndarray, max_dim: int = 768) -> Dict[str, Any]:
    """Generate browser-safe raster previews derived DIRECTLY from the real SAR GeoTIFF.

    Computes:
      - VV channel grayscale (percentile-stretched 2%..98% uint8 JPEG)
      - VH channel grayscale (percentile-stretched 2%..98% uint8 JPEG)
      - VV/VH/ratio false-color composite uint8 JPEG
      - U-Net predicted oil mask overlay (RGBA PNG, highlighting detected slick pixels)
    """
    import base64
    import io
    import rasterio
    from PIL import Image

    with rasterio.open(scene_path) as src:
        vv = src.read(1)
        vh = src.read(2)

    def to_u8(arr: np.ndarray) -> np.ndarray:
        p2, p98 = np.percentile(arr, (2, 98))
        scaled = np.clip((arr - p2) / (p98 - p2 + 1e-8) * 255.0, 0, 255).astype(np.uint8)
        return scaled

    vv_u8 = to_u8(vv)
    vh_u8 = to_u8(vh)
    ratio = vv / (vh + 1e-6)
    ratio_u8 = to_u8(ratio)
    comp = np.stack([vv_u8, vh_u8, ratio_u8], axis=-1)

    h, w = vv_u8.shape
    scale = min(max_dim / max(h, w), 1.0)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))

    buf_vv = io.BytesIO()
    Image.fromarray(vv_u8).resize((new_w, new_h), Image.Resampling.BILINEAR).save(buf_vv, format="JPEG", quality=85)

    buf_vh = io.BytesIO()
    Image.fromarray(vh_u8).resize((new_w, new_h), Image.Resampling.BILINEAR).save(buf_vh, format="JPEG", quality=85)

    buf_comp = io.BytesIO()
    Image.fromarray(comp).resize((new_w, new_h), Image.Resampling.BILINEAR).save(buf_comp, format="JPEG", quality=85)

    mask_rgba = np.zeros((h, w, 4), dtype=np.uint8)
    # Bright high-visibility coral-red overlay for detected oil slick pixels
    mask_rgba[mask == 1] = [255, 52, 52, 220]
    buf_mask = io.BytesIO()
    Image.fromarray(mask_rgba, mode="RGBA").resize((new_w, new_h), Image.Resampling.NEAREST).save(buf_mask, format="PNG")

    return {
        "width": new_w,
        "height": new_h,
        "vv": f"data:image/jpeg;base64,{base64.b64encode(buf_vv.getvalue()).decode('ascii')}",
        "vh": f"data:image/jpeg;base64,{base64.b64encode(buf_vh.getvalue()).decode('ascii')}",
        "composite": f"data:image/jpeg;base64,{base64.b64encode(buf_comp.getvalue()).decode('ascii')}",
        "mask": f"data:image/png;base64,{base64.b64encode(buf_mask.getvalue()).decode('ascii')}",
    }

