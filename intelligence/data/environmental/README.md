# intelligence/data/environmental — ocean current and wind data

| File pattern | Committed | Description |
|---|---|---|
| `README.md` | yes | this file |
| `demo_*` | **yes** (Phases 2/11) | bundled deterministic environmental field for `CASE-001` |
| anything else | no | external provider extracts/reanalyses are git-ignored |

## Variables used by the hindcast

| Variable | Symbol | Unit |
|---|---|---|
| surface current, eastward | `u_current` | m/s |
| surface current, northward | `v_current` | m/s |
| wind, eastward | `u_wind` | m/s |
| wind, northward | `v_wind` | m/s |
| wind speed | `windSpeed` | m/s (derived from the wind components) |
| wind direction | `windDirection` | degrees, meteorological convention (**to be confirmed when the live provider is integrated**) |

Each record also carries `timestamp` (UTC), `latitude`, `longitude`, and the grid resolution actually
used, so interpolated values remain traceable to their source.

## Demo implementation

`demo_environmental_field.json` (Phase 2) holds a small analytic, deterministic current+wind field on
a coarse grid covering the `CASE-001` study area. It is reproduced identically on every run, which is
what makes the demo reproducible, and it is labelled `DEMO DATA` in the UI.

## Live implementation (optional, out of prototype scope)

Copernicus Marine (currents) and ERA5/CDS (wind) are the candidate sources. Product identifiers,
endpoint URLs and authentication details are **not** recorded here because they have not been verified
against the official provider documentation — see `docs/data-sources.md` for status and
`docs/api-keys.md` for credential handling. Any live provider failure must fall back to the demo field
with a visible warning.