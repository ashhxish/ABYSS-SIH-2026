#!/usr/bin/env python3
"""ABYSS Phase 1 - real Sentinel-1 / U-Net adapter tests.

Covers the 16 Phase 1 test targets using the REAL checkpoint + REAL sample
(via ABYSS_SENTINEL1_MODEL_PATH) for inference-shape assertions, plus fast
pure-numpy/rasterio unit checks that never touch the model:

 1. model path configuration (+ env precedence)
 2. missing model error (no silent synthetic fallback)
 3. Sentinel-1 GeoTIFF validation (missing file, band count)
 4. VV/VH channel validation (2 bands, finite values)
 5. 256x256 patching (grid size, positions, edge exclusion)
 6. per-channel normalization (zero mean, unit variance)
 7. actual U-Net inference (real checkpoint + real 00999.tif)
 8. mask dimensions (H, W match source raster)
 9. threshold behaviour (0.5 binarisation of the probability map)
 10. polygonization (region count, GeoJSON validity, pixel-exactness)
 11. CRS handling (source EPSG:4326 preserved, lon/lat order)
 12. area calculation (geodesic, positive, consistent with mask)
 13. SatelliteObservation conversion (existing contract, sensor metadata)
 14. provenance (Sentinel-1 SAR, non-synthetic, model hash, patch/threshold)
 15. missing acquisition timestamp (None + explicit warning, never invented)
 16. CASE-001 regression (synthetic pipeline untouched)
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import numpy as np

INTELLIGENCE_DIR = Path(__file__).resolve().parent.parent
if str(INTELLIGENCE_DIR) not in sys.path:
    sys.path.insert(0, str(INTELLIGENCE_DIR))

from app.detection import sentinel1
from app.detection.sentinel1 import (
    MODEL_ENV_VAR,
    PATCH_SIZE,
    THRESHOLD,
    Sentinel1Error,
    combine_geometry,
    create_patches,
    geodesic_area_km2,
    is_geographic_crs,
    label_regions,
    normalize_patch,
    resolve_model_path,
    result_warnings,
    to_satellite_observation,
)

REAL_MODEL = Path("/home/ashish/SIH/sentinel1_integration/best_unet_oil_spill.pth")
REAL_SCENE = Path("/home/ashish/SIH/sentinel1_integration/00999.tif")
REAL_AVAILABLE = REAL_MODEL.is_file() and REAL_SCENE.is_file()


def _require_real(testcase):
    if not REAL_AVAILABLE:
        testcase.skipTest("real Sentinel-1 assets not present")
    for mod in ("torch", "rasterio", "scipy", "shapely", "pyproj"):
        try:
            __import__(mod)
        except ImportError:
            testcase.skipTest(f"{mod} not installed")


class TestModelPathConfiguration(unittest.TestCase):
    """Targets 1-2: ABYSS_SENTINEL1_MODEL_PATH config + loud missing-model error."""

    def test_env_var_selects_checkpoint(self):
        if not REAL_MODEL.is_file():
            self.skipTest("real checkpoint not present")
        old = os.environ.get(MODEL_ENV_VAR)
        os.environ[MODEL_ENV_VAR] = str(REAL_MODEL)
        try:
            self.assertEqual(resolve_model_path(), REAL_MODEL)
        finally:
            if old is None:
                os.environ.pop(MODEL_ENV_VAR, None)
            else:
                os.environ[MODEL_ENV_VAR] = old

    def test_explicit_argument_beats_environment(self):
        old = os.environ.get(MODEL_ENV_VAR)
        os.environ[MODEL_ENV_VAR] = "/nonexistent/env-checkpoint.pth"
        try:
            if REAL_MODEL.is_file():
                self.assertEqual(resolve_model_path(str(REAL_MODEL)), REAL_MODEL)
        finally:
            if old is None:
                os.environ.pop(MODEL_ENV_VAR, None)
            else:
                os.environ[MODEL_ENV_VAR] = old

    def test_missing_model_raises_useful_error(self):
        old = os.environ.pop(MODEL_ENV_VAR, None)
        try:
            with self.assertRaises(Sentinel1Error) as ctx:
                resolve_model_path("/nonexistent/missing-checkpoint.pth")
            message = str(ctx.exception)
            self.assertIn("not found", message)
            self.assertIn("synthetic", message)  # no silent fallback, ever
        finally:
            if old is not None:
                os.environ[MODEL_ENV_VAR] = old

    def test_unset_env_var_raises_useful_error(self):
        old = os.environ.pop(MODEL_ENV_VAR, None)
        try:
            with self.assertRaises(Sentinel1Error) as ctx:
                resolve_model_path()
            self.assertIn(MODEL_ENV_VAR, str(ctx.exception))
        finally:
            if old is not None:
                os.environ[MODEL_ENV_VAR] = old

    def test_no_hardcoded_home_path_in_adapter(self):
        source = Path(sentinel1.__file__).read_text(encoding="utf-8")
        self.assertNotIn("/home/ashish", source)
        self.assertNotIn("/home/", source)


class TestRasterValidation(unittest.TestCase):
    """Targets 3-4: GeoTIFF + VV/VH channel validation."""

    def test_missing_scene_raises(self):
        with self.assertRaises(Sentinel1Error) as ctx:
            sentinel1.read_sentinel1(Path("/nonexistent/scene.tif"))
        self.assertIn("not found", str(ctx.exception))

    def test_real_scene_has_two_bands_and_crs(self):
        _require_real(self)
        image, info = sentinel1.read_sentinel1(REAL_SCENE)
        self.assertEqual(image.shape[0], 2)  # VV + VH
        self.assertEqual((info.width, info.height), (image.shape[2], image.shape[1]))
        self.assertEqual(image.dtype, np.float32)
        self.assertTrue(np.all(np.isfinite(image)))
        self.assertIn("4326", info.crs)
        left, bottom, right, top = info.bounds
        self.assertLess(left, right)
        self.assertLess(bottom, top)

    def test_single_band_scene_rejected(self):
        _require_real(self)
        import rasterio
        from rasterio.transform import from_origin
        single = Path("/tmp/s1_oneband.tif")
        data = np.zeros((1, 64, 64), dtype=np.float32)
        with rasterio.open(str(single), "w", driver="GTiff", height=64, width=64,
                           count=1, dtype="float32",
                           crs="EPSG:4326", transform=from_origin(0, 0, 0.01, 0.01)) as dst:
            dst.write(data)
        try:
            with self.assertRaises(Sentinel1Error) as ctx:
                sentinel1.read_sentinel1(single)
            self.assertIn("2 bands", str(ctx.exception))
        finally:
            single.unlink(missing_ok=True)


class TestPatchingAndNormalization(unittest.TestCase):
    """Targets 5-6: 256x256 patching + per-channel normalization."""

    def test_patch_grid_matches_teammate_behaviour(self):
        rng = np.random.default_rng(7)
        image = rng.normal(size=(2, 600, 520)).astype(np.float32)
        patches, positions = create_patches(image)
        # range(0, 600-256+1, 256) -> rows {0, 256}; cols {0, 256} -> 2x2
        self.assertEqual(len(patches), 4)
        self.assertEqual(positions, [(0, 0), (0, 256), (256, 0), (256, 256)])
        for patch in patches:
            self.assertEqual(patch.shape, (2, PATCH_SIZE, PATCH_SIZE))
        # edge pixels excluded, never padded
        covered_h = 2 * PATCH_SIZE
        covered_w = 2 * PATCH_SIZE
        self.assertLessEqual(covered_h, 600)
        self.assertLessEqual(covered_w, 520)

    def test_exact_multiple_tiles_fully(self):
        image = np.zeros((2, 512, 512), dtype=np.float32)
        patches, _ = create_patches(image)
        self.assertEqual(len(patches), 4)

    def test_per_channel_normalization(self):
        patch = np.stack([
            np.full((8, 8), 5.0, dtype=np.float32) + np.arange(64, dtype=np.float32).reshape(8, 8),
            np.full((8, 8), -3.0, dtype=np.float32),
        ])
        out = normalize_patch(patch)
        self.assertAlmostEqual(float(out[0].mean()), 0.0, places=5)
        self.assertAlmostEqual(float(out[0].std()), 1.0, places=5)
        # constant channel: std == 0 -> (x - mean)/eps == 0, never NaN/inf
        self.assertTrue(np.all(np.isfinite(out[1])))
        self.assertTrue(np.all(out[1] == 0.0))

    def test_real_scene_patch_count(self):
        _require_real(self)
        image, info = sentinel1.read_sentinel1(REAL_SCENE)
        patches, _ = create_patches(image)
        self.assertEqual(len(patches), (info.height // 256) * (info.width // 256))
        self.assertEqual(len(patches), 8 * 8)


class TestRealInference(unittest.TestCase):
    """Targets 7-9: ACTUAL U-Net inference on 00999.tif + mask + threshold."""

    @classmethod
    def setUpClass(cls):
        _require_real_check = REAL_AVAILABLE
        if not _require_real_check:
            raise unittest.SkipTest("real Sentinel-1 assets not present")
        for mod in ("torch", "rasterio", "scipy", "pyproj"):
            try:
                __import__(mod)
            except ImportError:
                raise unittest.SkipTest(f"{mod} not installed")
        from app.detection.unet import UNet  # noqa: F401  (architecture import check)
        image, cls.info = sentinel1.read_sentinel1(REAL_SCENE)
        model, device = sentinel1.load_unet(REAL_MODEL)
        probability, mask = sentinel1.run_inference(image, model, device)
        cls.probability = probability
        cls.mask = mask

    def test_unet_loads_real_checkpoint_weights(self):
        import torch
        state = torch.load(str(REAL_MODEL), map_location="cpu")
        self.assertIn("model_state_dict", state)
        self.assertEqual(tuple(state["model_state_dict"]["enc1.block.0.weight"].shape), (64, 2, 3, 3))

    def test_mask_dimensions_match_source(self):
        self.assertEqual(self.mask.shape, (self.info.height, self.info.width))
        self.assertEqual(self.probability.shape, (self.info.height, self.info.width))

    def test_probability_range_and_threshold(self):
        self.assertGreaterEqual(float(self.probability.min()), 0.0)
        self.assertLessEqual(float(self.probability.max()), 1.0)
        expect = (self.probability >= THRESHOLD).astype(np.uint8)
        np.testing.assert_array_equal(self.mask, expect)
        self.assertTrue(set(np.unique(self.mask)).issubset({0, 1}))
        self.assertGreater(int(self.mask.sum()), 0)  # real spill detected

    def test_mask_is_deterministic(self):
        import torch
        torch.manual_seed(0)
        np.random.seed(0)
        image, _ = sentinel1.read_sentinel1(REAL_SCENE)
        model, device = sentinel1.load_unet(REAL_MODEL)
        _, mask2 = sentinel1.run_inference(image, model, device)
        np.testing.assert_array_equal(self.mask, mask2)
class TestGeospatialProcessing(unittest.TestCase):
    """Targets 10-12: polygonization, CRS handling, geodesic area."""

    @classmethod
    def setUpClass(cls):
        if not REAL_AVAILABLE:
            raise unittest.SkipTest("real Sentinel-1 assets not present")
        for mod in ("torch", "rasterio", "scipy", "pyproj"):
            try:
                __import__(mod)
            except ImportError:
                raise unittest.SkipTest("%s not installed" % mod)
        image, cls.info = sentinel1.read_sentinel1(REAL_SCENE)
        model, device = sentinel1.load_unet(REAL_MODEL)
        _, mask = sentinel1.run_inference(image, model, device)
        labelled, descriptors = label_regions(mask)
        cls.regions = sentinel1.polygonize_regions(labelled, descriptors, cls.info)
        cls.mask = mask

    def test_regions_kept_and_ordered(self):
        self.assertGreater(len(self.regions), 0)
        pixels = [r.pixels for r in self.regions]
        self.assertEqual(pixels, sorted(pixels, reverse=True))
        self.assertEqual(sum(pixels), int(self.mask.sum()))

    def test_geometry_valid_lon_lat_order(self):
        left, bottom, right, top = self.info.bounds
        for region in self.regions:
            self.assertEqual(region.geometry["type"], "Polygon")
            ring = region.geometry["coordinates"][0]
            self.assertGreaterEqual(len(ring), 4)
            self.assertEqual(ring[0], ring[-1])
            for lon, lat in ring:
                self.assertGreaterEqual(lon, left - 1e-6)
                self.assertLessEqual(lon, right + 1e-6)
                self.assertGreaterEqual(lat, bottom - 1e-6)
                self.assertLessEqual(lat, top + 1e-6)
            self.assertGreaterEqual(region.centroid_lon, left - 1e-6)
            self.assertLessEqual(region.centroid_lon, right + 1e-6)
            self.assertGreaterEqual(region.centroid_lat, bottom - 1e-6)
            self.assertLessEqual(region.centroid_lat, top + 1e-6)

    def test_crs_preserved(self):
        self.assertTrue(is_geographic_crs(self.info.crs))
        self.assertIn("4326", self.info.crs)

    def test_geodesic_area_positive_and_consistent(self):
        for region in self.regions:
            self.assertGreater(region.area_km2, 0.0)
        total = sum(r.area_km2 for r in self.regions)
        self.assertGreater(total, 0.0)
        self.assertLess(total, 500.0)
        ring = self.regions[0].geometry["coordinates"][0]
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        geo = geodesic_area_km2(xs, ys)
        deg2 = abs(sum(xs[i] * ys[(i + 1) % len(xs)]
                       - xs[(i + 1) % len(xs)] * ys[i]
                       for i in range(len(xs))) / 2.0)
        self.assertNotAlmostEqual(geo, deg2, places=3)
        self.assertAlmostEqual(geo, self.regions[0].area_km2, places=6)

    def test_combine_geometry_is_deterministic(self):
        first = combine_geometry(self.regions)
        second = combine_geometry(list(reversed(self.regions)))
        self.assertEqual(first["type"], second["type"])
        self.assertEqual(first, combine_geometry(self.regions))
class TestObservationConversion(unittest.TestCase):
    """Targets 13-15: contract conversion, provenance, unknown timestamp."""

    @classmethod
    def setUpClass(cls):
        if not REAL_AVAILABLE:
            raise unittest.SkipTest("real Sentinel-1 assets not present")
        for mod in ("torch", "rasterio", "scipy", "pyproj"):
            try:
                __import__(mod)
            except ImportError:
                raise unittest.SkipTest("%s not installed" % mod)
        old = os.environ.get(MODEL_ENV_VAR)
        os.environ[MODEL_ENV_VAR] = str(REAL_MODEL)
        try:
            cls.result = sentinel1.detect_scene(REAL_SCENE)
        finally:
            if old is None:
                os.environ.pop(MODEL_ENV_VAR, None)
            else:
                os.environ[MODEL_ENV_VAR] = old
        cls.obs = to_satellite_observation(cls.result)

    def test_uses_existing_contract(self):
        from app.ingestion.contracts import SatelliteObservation
        self.assertIsInstance(self.obs, SatelliteObservation)
        self.assertIn(self.obs.geometry["type"], ("Polygon", "MultiPolygon"))
        self.assertIn("lat", self.obs.centroid)
        self.assertIn("lon", self.obs.centroid)
        self.assertEqual(self.obs.sensor["platform"], "Sentinel-1")
        self.assertEqual(self.obs.sensor["bands"], ["VV", "VH"])
        self.assertIsNone(self.obs.detectionConfidence)
        scenario = self.obs.to_detection_scenario()
        for key in ("acquisitionTime", "geometry", "sensor", "synthetic",
                    "datasetLabel", "provenance", "caseId"):
            self.assertIn(key, scenario)

    def test_provenance_marks_real_source(self):
        prov = self.obs.provenance
        self.assertFalse(prov.synthetic)
        self.assertEqual(prov.sourceType, "satellite")
        self.assertIn("Sentinel-1", prov.sourceName)
        self.assertEqual(prov.sourceFile, str(REAL_SCENE))
        chars = self.obs.characteristics
        self.assertEqual(chars["patchSize"], 256)
        self.assertEqual(chars["threshold"], 0.5)
        self.assertEqual(chars["modelName"], "best_unet_oil_spill.pth")
        self.assertEqual(len(chars["modelSha256"]), 64)
        self.assertIn("normalisation", chars["preprocessing"])

    def test_acquisition_time_unknown_with_warning(self):
        self.assertIsNone(self.obs.acquisitionTime)
        warnings = result_warnings(self.result)
        self.assertTrue(any("acquisition time unknown" in w for w in warnings))
        self.assertTrue(any("processed_at" in w for w in warnings))
        scenario = self.obs.to_detection_scenario()
        self.assertIsNone(scenario["acquisitionTime"])


class TestCase001Regression(unittest.TestCase):
    """Target 16: the synthetic CASE-001 pipeline is untouched."""

    def test_demo_slick_still_loads(self):
        from app.detection.satellite import DemoSatelliteProvider
        from app.config import get_settings
        settings = get_settings()
        provider = DemoSatelliteProvider.for_case(settings.demo_case_dir)
        scenario = provider.fetch()
        self.assertEqual(scenario.get("caseId"), "CASE-001")
        self.assertTrue(scenario.get("synthetic"))
        self.assertEqual(scenario.get("acquisitionTime"), "2026-03-14T06:00:00Z")

    def test_case001_investigation_baseline(self):
        from app.investigation import run_investigation
        result = run_investigation()
        payload = result.to_dict()
        entries = payload["ranking"]["entries"]
        self.assertEqual(len(entries), 12)
        self.assertEqual(entries[0]["mmsi"], "900000001")
        self.assertAlmostEqual(entries[0]["totalScore"], 83.564, places=2)
        self.assertEqual(entries[1]["mmsi"], "900000002")


if __name__ == "__main__":
    unittest.main()
