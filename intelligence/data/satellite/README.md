# intelligence/data/satellite — satellite / SAR assets

| File pattern | Committed | Description |
|---|---|---|
| `README.md` | yes | this file |
| `demo_*` | **yes** (Phase 12) | bundled demonstration SAR scene preview + its pre-computed slick polygon |
| anything else | no | real SAR scenes are large and licence-bound — git-ignored |

## Demo assets planned for Phase 12

* `demo_sar_scene.png` — small, legally usable demonstration image used for display in the dashboard.
* `demo_slick_polygon.geojson` — the pre-computed slick polygon for `CASE-001` (deterministic).
* `demo_scene_metadata.json` — acquisition timestamp, footprint bounds, sensor description, and an
  explicit `synthetic: true` marker where applicable.

## Notes

* Raw downloaded scenes (`*.tif`, `*.nc`, `*.zip`, …) are git-ignored; only `demo_*` assets are
  committed.
* Real SAR access (for example Sentinel-1 via Copernicus Data Space) requires credential handling and
  licence review — see `docs/data-sources.md` and `docs/api-keys.md`. The authentication method is
  **not verified** in this repository and must not be guessed.
* Demo mode never downloads imagery; it uses the bundled assets so the pipeline is reproducible offline.