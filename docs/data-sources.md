# ABYSS — Data sources and provider abstraction

Status: **Phase 1**. This document lists what ABYSS intends to use and — importantly — what has and
has not been verified. **No endpoint URL, token format or registration URL is invented here.**

## 1. Rule

Every data source sits behind an interface, so that demo mode is always available and a provider can
be replaced without touching the pipeline:

```
SatelliteDataProvider        -> DemoSatelliteProvider | (later) CopernicusSentinel1Provider
EnvironmentalDataProvider    -> DemoEnvironmentalProvider | (later) CopernicusMarineProvider | (later) ERA5Provider
AISDataProvider              -> DemoAISProvider | (later) LicensedAISProvider
```

Each resolved provider reports its identity in every response (`dataSource`), so the UI can print
`DEMO DATA` or the real provider name, plus `warnings[]` on fallback.

## 2. Satellite / SAR

| Item | Value |
|---|---|
| Intended sensor family | C-band SAR (Sentinel-1) — appropriate for slick detection |
| Demo implementation | bundled pre-computed slick polygon + bundled imagery (`intelligence/data/demo/`) |
| Real implementation | `CopernicusSentinel1Provider` (*Phase 20, optional*) |
| Authentication | **Authentication method needs verification from the official provider documentation.** Copernicus Data Space access flows have changed over time (OAuth2 vs legacy credentials); do not assume. |
| Env vars | `COPERNICUS_USERNAME`, `COPERNICUS_PASSWORD` (placeholders only in `.env.example`) |
| Fallback | demo slick geometry + `lookAlikeWarning` flag |

Demo mode never downloads imagery: the demonstration case ships a small, legally usable image and
its polygon so the pipeline is reproducible offline.

## 3. Environmental (ocean currents and wind)

Required model inputs: surface current U/V components, wind speed and direction (wind U/V, windage),
timestamped and located near the slick.

| Candidate source | Variables | Status |
|---|---|---|
| Copernicus Marine Service (CMEMS) | surface currents (e.g. global/regional ocean physics products) | candidate; **auth + product IDs need verification** |
| Copernicus Climate Data Store (ERA5) | 10 m wind U/V, historical reanalysis | candidate; **auth + API details need verification** |
| Bundled deterministic field | divergence-free analytic current + wind field | **implemented in demo mode** |

* Do **not** invent product identifiers, dataset names or endpoint URLs. Record them only after
  reading the official provider documentation.
* Spatial and temporal interpolation (*Phase 11*) is performed on a grid loaded by the provider, so
  swapping the source does not change the hindcast code.
* Fallback: the deterministic demo field plus a visible warning; the hindcast output is marked
  `dataSource: demo`.

## 4. AIS

| Item | Value |
|---|---|
| Demo implementation | bundled synthetic CSV: `intelligence/data/demo/case_001/ais/demo_ais_positions.csv` (*Phase 2, committed*) |
| Demo contents | 12 synthetic vessels, 3,669 records, 72 h, 11 required AIS fields + `datasetLabel`; see `intelligence/data/demo/case_001/README.md` |
| Real implementation | `LicensedAISProvider` (*out of prototype scope*) |
| Authentication | **Authentication method needs verification from the official provider documentation.** Historical AIS is generally commercial and licensed; ABYSS ships no credentials, endpoints or scrapers. |
| Env vars | none defined until a provider is actually chosen (no fake variables are created) |
| Fallback | synthetic demo CSV, clearly labelled |

Mandatory labelling: any AIS-derived view states **"AIS: Synthetic Demonstration Dataset"** in demo
mode. Synthetic AIS is never presented as real-world evidence, and synthetic MMSI/IMO/vessel names
must not be traceable to real vessels.

Expected AIS fields (*Phase 3*): `MMSI, IMO, vesselName, vesselType, timestamp (UTC), latitude,
longitude, SOG, COG, heading, navigationStatus`. Cleaning normalises types/timestamps/identifiers,
sorts chronologically, removes invalid coordinates, impossible speeds, malformed timestamps and
duplicates — and **logs every removal with a reason and a count** instead of silently dropping rows.

## 5. Reference geodata

| Data | Purpose | Status |
|---|---|---|
| Coastline / land polygons | context and plausibility checks (a vessel track crossing land is suspect) | **verification needed** for licence; demo geometry is synthetic |
| Exclusive Economic Zone boundaries | optional context for investigators | optional, licence **verification needed** |

Neither is required for the demo pipeline.

## 6. Provenance and honesty requirements

Every analysis response carries enough metadata for the UI and report to distinguish:

1. **Observed data** — e.g. AIS positions from the dataset, the SAR acquisition timestamp.
2. **Model-derived estimates** — origin region, release time window, drift trajectories.
3. **Inferred compatibility** — spatial/temporal/trajectory/gap reasoning and its scores.
4. **Uncertainty** — detection confidence, origin confidence, AIS evidence confidence, investigation
   confidence, each reported separately rather than blended into one number.
