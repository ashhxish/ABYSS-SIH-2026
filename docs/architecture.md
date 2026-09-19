# ABYSS — Architecture

Status: **Phase 1 (structure)**. This document describes the target architecture; sections marked
*Phase N* are implemented in that phase. Anything not yet verified is marked as such.

## 1. Components

```
                    React + Vite + React-Leaflet + Recharts      (frontend/,  port 5173)
                                   |
                                   | REST /api/**   (JSON, GeoJSON geometries)
                                   v
                     Spring Boot (Java 21)                        (backend/,   port 8080)
                     - case lifecycle + step orchestration
                     - JPA persistence, report assembly
                     - the only public API surface
                                   |
                                   | REST (internal, not exposed to the browser)
                                   v
                   Python 3.11+ FastAPI                           (intelligence/, port 8000)
                   - detection / characterisation
                   - hindcast (backward particle drift)
                   - AIS clean -> trajectory -> filter -> behaviour -> gaps -> score
                                   |
                                   v
                    PostgreSQL 16 + PostGIS                       (database/, port 5432)
```

Design rules:

* **The browser only talks to the backend.** The Python service is an internal dependency, so the
  public contract stays stable and CORS stays trivial.
* The intelligence service is **stateless per request** in demo mode (deterministic functions over
  bundled data), so it can be restarted mid-demo without losing anything.
* Persistence is owned by the backend; the intelligence service returns results and does not write
  domain tables. (*Phase 14* may add read-only access for bulk AIS loading.)

## 2. Analysis pipeline (the product itself)

```
1  satellite observation            SAR scene + metadata (footprint, acquisition time, bounds)
2  oil-spill detection              dark-formation candidates + confidence + look-alike warning
3  slick characterisation           area, centroid, bbox, perimeter, length, width, orientation
4  environmental data               surface current U/V, wind speed/direction, U/V components
5  backward drift / hindcasting     particle ensemble integrated backwards in time
6  probable origin + uncertainty    origin density region + release time window + confidence
7  AIS ingestion                    CSV load, normalise, validate, log cleaning statistics
8  trajectory construction          per-vessel ordered track, distances, speed, course changes
9  candidate filtering              spatial -> temporal -> trajectory compatibility
10 behaviour analysis               slowdown, loitering, course deviation vs the vessel's own baseline
11 AIS gap analysis                 gaps contextualised: could the vessel cross the origin region?
12 explainable evidence scoring     weighted, configurable factors + human-readable reasons
13 candidate ranking                ordered list with per-factor breakdown
14 forensic timeline                per-vessel event sequence around the estimated release window
15 evidence chain                   traceable graph from observation to score
16 dashboard / report               map-centric UI + investigation report with limitations
```

## 3. Module responsibilities

### frontend/ (*Phase 15*)
Pages: Investigation Overview, Satellite Detection, Origin Reconstruction, AIS Vessel Investigation,
Candidate Ranking, Vessel Detail, Forensic Timeline, Evidence Chain, Investigation Report.
Directories: `components/` (shared UI), `pages/`, `maps/` (Leaflet layers), `charts/` (Recharts),
`services/` (API clients), `data/` (offline fallbacks for UI development).
Map layers: satellite footprint, detected slick, slick boundary, probable origin region, hindcast
particles, vessel trajectories, candidate tracks, AIS gap segments, environmental vectors.

### backend/ (*Phase 13*)
`controller/` REST endpoints from the specification contract · `service/` case orchestration and
calls to the intelligence service · `repository/` Spring Data JPA · `entity/` domain mapping ·
`dto/` request/response models · `config/` CORS, Jackson, HTTP client, startup validation ·
`exception/` typed errors mapped by `@RestControllerAdvice` to meaningful JSON errors.

### intelligence/ (*Phases 3–12*)
`config.py` validated environment settings and `geo.py` shared geodesy helpers (both Phase 3) ·
`detection/` slick detection + characterisation · `hindcast/` backward particle drift ·
`ais/cleaning.py` **implemented in Phase 3** (ingestion, validation, audit trail); `ais/` still gains
trajectory construction, spatial/temporal/trajectory filtering and gap analysis in Phases 4–9 ·
`behaviour/` baseline comparison and anomaly scoring · `scoring/` configurable evidence weighting +
counterfactual reasons · `schemas/` Pydantic models = API contract · `tests/` dataset tests (Phase 2)
and cleaning tests (Phase 3), plus the forensic test cases A–G in Phase 19.
Data: `data/satellite|environmental|ais|demo` (demo assets committed, raw downloads ignored).

## 4. Data modes and fallback policy

`ABYSS_DATA_MODE` selects `demo` (default) or `live`. The provider abstraction (see
`docs/data-sources.md`) is resolved at startup:

1. `live` + provider configured → use it.
2. `live` + provider unconfigured or failing → **log a WARNING, use the demo provider, and mark the
   response with a machine-readable `dataSource` / `warnings[]` field** so the UI can display, for
   example, *"Environmental data unavailable — using demonstration dataset."*
3. `demo` → demo provider only; no network call is ever attempted.

Hard requirements: demo mode works with zero credentials; no external failure may crash a request;
synthetic data is always labelled; timestamps are UTC (`TIMESTAMPTZ`) end to end.

## 5. Configuration summary

| Variable | Consumer | Default | Notes |
|---|---|---|---|
| `ABYSS_DATA_MODE` | all | `demo` | `demo` or `live` |
| `POSTGRES_HOST/PORT/DB/USER/PASSWORD` | backend | localhost / 5432 / abyss / abyss / placeholder | ABYSS-owned, not a third-party secret |
| `BACKEND_PORT` | backend | 8080 | |
| `ABYSS_INTELLIGENCE_BASE_URL` | backend | http://localhost:8000 | |
| `CORS_ALLOWED_ORIGINS` | backend | http://localhost:5173 | |
| `INTELLIGENCE_PORT`, `INTELLIGENCE_LOG_LEVEL` | intelligence | 8000, INFO | |
| `VITE_ABYSS_API_BASE_URL` | frontend | http://localhost:8080 | only `VITE_`-prefixed vars reach the browser |
| `COPERNICUS_*`, `CDS_*` | intelligence | empty | live mode only; **auth method needs verification** |

Secrets never appear in source: configuration is read from the environment, validated at startup, and
`.env` is git-ignored.

## 6. Error handling and logging

* Backend: typed exceptions → meaningful HTTP statuses (`404` unknown case, `502` intelligence
  service unreachable, `422` invalid request body).
* Intelligence: every stage reports `warnings[]`; a failing optional provider degrades instead of
  aborting. A failing **required** stage (for example a missing AIS CSV) returns a clear error.
* Logged events: provider/API errors, invalid AIS rows with the reason, missing environmental values,
  model failures, and every fallback activation.

## 7. Confidence model (reported separately, never blended)

| Confidence | Meaning | Produced by |
|---|---|---|
| Detection confidence | how strongly the observed dark formation behaves like an oil slick rather than a look-alike (low wind, biogenic film, radar artefact) | detection (*Phase 12*) |
| Origin reconstruction confidence | how tightly the backward particle ensemble agrees on the probable origin region and release window | hindcast (*Phase 11*) |
| AIS evidence confidence | completeness/quality of the AIS data available for a candidate (gap fraction, position density) | AIS pipeline (*Phases 3–9*) |
| Investigation confidence | summary of the case, derived with an explicit stated rule rather than a blind average | scoring + report (*Phases 10, 18*) |

The UI shows these four values separately.

## 8. Non-goals (deliberate prototype boundaries)

No Kubernetes, Kafka, Redis, object storage, service mesh or cloud deployment; no global-scale AIS
processing (analysis is scoped to a defined investigation area); no claim of legal proof. Docker
Compose is provided only as an optional local PostGIS convenience and is not required by any ABYSS
phase.

