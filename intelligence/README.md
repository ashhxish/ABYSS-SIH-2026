# intelligence/ — ABYSS FastAPI intelligence service

Python 3.11+ · FastAPI · NumPy · Pandas · SciPy · Shapely · GeoPandas (only if needed). Internal
service; the browser never calls it directly.

```
intelligence/
├── requirements.txt                 (Phase 3: pandas, numpy — pinned to installed versions)
├── app/
│   ├── __init__.py
│   ├── config.py                    env-driven settings + startup validation   (Phase 3)
│   ├── geo.py                       shared geodesy helpers                     (Phase 3)
│   ├── main.py                      FastAPI app + routers             (Phases 11-13)
│   ├── detection/                   SAR slick detection + look-alikes  (Phase 12)
│   ├── hindcast/                    backward particle drift model      (Phase 11)
│   ├── ais/
│   │   ├── __init__.py
│   │   └── cleaning.py              ingestion, validation, audit trail   (Phase 3 ✅)
│   │                                (Phase 4 adds trajectory construction here)
│   ├── behaviour/                   baseline comparison, anomalies     (Phase 8)
│   ├── scoring/                     configurable weights, reasons, counterfactuals (Phase 10)
│   ├── providers/                   Satellite/Environmental/AIS provider abstractions
│   │                                + Demo* implementations            (Phase 2+)
│   └── schemas/                     Pydantic models = the service contract
├── data/
│   ├── satellite/                   demo scene + README (raw downloads ignored)
│   ├── environmental/               demo field + README
│   ├── ais/                         README: where AIS datasets live (demo extract is inside the
│   │                                case bundle at data/demo/case_001/ais/)
│   └── demo/
│       ├── generate_case_001.py     deterministic dataset generator    (Phase 2 ✅)
│       └── case_001/                the generated CASE-001 bundle      (Phase 2 ✅)
└── tests/                           dataset tests (Phase 2) + cleaning tests (Phase 3)
```

## Internal API (specification contract)

Low-level endpoints for testing: `POST /detect`, `/characterize`, `/hindcast`, `/ais/clean`,
`/ais/trajectory`, `/ais/filter`, `/ais/behaviour`, `/ais/gaps`, `/score`.
One high-level endpoint for the demo: **`POST /investigate`** runs the whole pipeline.
Plus `GET /health` and `GET /data-sources` (which provider is active and whether demo data is in use).

## Rules for this module

1. **DEMO MODE MUST RUN WITH ZERO CREDENTIALS** and make no network calls.
2. Every response carries `dataSource` and `warnings[]` so the UI can label demo data and fallbacks.
3. Deterministic in demo mode: fixed seeds, bundled inputs; repeated runs return identical output.
4. No provider failure may raise out of the pipeline: degrade to demo data and log the reason.
5. AIS cleaning must report counts and reasons per rejection category (`cleaningStatistics`).
6. An AIS gap never scores on its own — only when physically compatible with the origin region and
   release window.
7. Distances use geodesic calculations, not planar Euclidean.
8. `docs/methodology.md` is the authoritative statement of what may and may not be claimed.

## AIS cleaning (Phase 3 — implemented)

`app/ais/cleaning.py` turns a raw AIS CSV into normalised, validated, time-ordered records **plus a
complete audit trail**. It is documentation-complete in its module docstring; the essentials:

| Aspect | Behaviour |
|---|---|
| Rejection categories (row unusable) | `missing_required_field`, `malformed_timestamp`, `invalid_coordinate`, `missing_vessel_identifier`, `invalid_vessel_identifier`, `duplicate_record`, `impossible_speed` |
| Removed values (row kept, one field nulled) | `invalid_speed_value`, `invalid_course_value`, `invalid_heading_value`, `invalid_navigation_status_value`, `not_available_sentinel` |
| Row warnings (row kept, quality note) | `missing_optional_field`, `conflicting_position_same_timestamp`, `invalid_imo`, `unknown_vessel_type`, `missing_vessel_name`, `timestamp_assumed_utc` |
| Traceability | every rejected row and removed value carries `sourceLine` (1-based file line), category, reason and the raw values |
| Thresholds | `CleaningConfig` (impossible speed default **60 kn**, prototype and configurable; AIS "not available" sentinel handling can be switched off) |
| Determinism | identical input gives byte-identical output, including audit ordering |
| Output | `records[]`, `vessels[]`, `rejected[]`, `removedValues[]`, `statistics`, `warnings[]`, `notes[]`, `config`, `source` |

Nothing in this module concludes anything about a vessel: it records only what the data does and does
not contain. Results on the synthetic CASE-001 extract: **3,675 rows in → 3,666 records, 9 rejected
(4 duplicate / 2 malformed timestamp / 2 invalid coordinate / 1 impossible speed), 1 value removed,
4 rows flagged**, all predicted by the Phase 2 defect inventory before the code was written.

## AIS trajectory construction (Phase 4 — implemented)

`app/ais/trajectory.py` turns cleaned records into per-vessel **`VesselTrajectory`** objects. It is
the phase that makes movement measurable, so it is deliberately restricted to *description*: it
produces facts about where a vessel was and how fast it moved, and no judgement about whether that
matters.

| Aspect | Behaviour |
|---|---|
| Grouping | one trajectory per MMSI (IMO/name/type retained as metadata) |
| Ordering | chronological; same-timestamp positions keep cleaning's deterministic order |
| `points[]` | index, timestamp, epochSeconds, lat, lon, sogKn, cogDeg, headingDeg, navigationStatus, `sourceLine` (traces back to the CSV line) |
| `segments[]` | consecutive-record great-circle distance, elapsed seconds, **implied speed**, initial bearing, reported SOG |
| `gaps[]` | interval with no records (default ≥ 1800 s), the last position before and the next after, straight-line distance, **implied speed**, and whether that implied speed exceeds the configured maximum |
| `stopSlowPeriods[]` | descriptive low-speed periods (stop < 0.5 kn, slow < 3.0 kn) with duration and median speed |
| `courseChanges[]` | signed/absolute turn ≥ 30° between consecutive segments, with timestamps |
| `stats` | observed distance, max/average reported SOG, duration, stop/slow counts, gap counts, course-change count |
| `geometry` | GeoJSON LineString of the whole track |
| `geometryByLeg` | LineStrings **split at every gap**, so a map never draws a straight line through unobserved time |
| Thresholds | `TrajectoryConfig` (gap, stop, slow, course-change) — configurable prototype values, reported in every result |

Three properties are enforced because later phases depend on them:

1. **Geodesic distances.** Travel is summed great-circle distance over contiguous runs; the straight
   line across a gap is reported as its own field and **never counted as observed travel**.
2. **No drawing through silence.** `geometryByLeg` exists precisely so a rendered track cannot imply
   continuous observation across an AIS gap.
3. **Physical self-consistency.** Reported speed over ground agrees with the distance actually covered
   on every consecutive record pair, because trajectory compatibility and gap feasibility are both
   arguments about implied speed. Both the generator and the test suite assert this; measured on the
   delivered dataset the worst disagreement is **0.83 % at ≥ 5 kn** and **0.61 % at ≥ 8 kn**. Below
   that the SOG column's 0.1 kn resolution itself dominates (2.0 kn ± 0.05 kn is ±2.5 %), which is why
   the consistency tests apply a stated speed floor.

A gap record carries the facts and an explicit `note` that relevance is decided in the AIS gap
analysis phase. A test asserts no field name in a gap mentions score, relevance, suspicion or rank,
so the boundary between measurement and inference cannot erode silently.

Results on the synthetic CASE-001 extract (after cleaning):

| | |
|---|---|
| Trajectories | **12** (from 3,666 records) |
| Segments | 3,652 |
| Gaps | **2** — both `2026-03-13T11:55Z → 16:00Z` (4.08 h) |
| Gap feasibility | V002 **79.4 km → 10.5 kn** (within a tanker's normal speed); V003 **265.8 km → 35.1 kn** (unrealistic) |
| stop / slow periods | 12 / 14 (all descriptive: berths, fishing grounds, harbour work) |
| Course changes ≥ 30° | 64 |
| Observed travel | 7,469 km (straight line across gaps excluded) |

The V002/V003 pair is the fixture that makes "a gap alone is never suspicion" testable: **identical
gap timing, identical location at gap start, only physical feasibility differs.**

## Commands

```bash
# from the repository root (all Python commands need the project virtual environment)
.venv/bin/python intelligence/app/ais/cleaning.py                 # clean the demo extract + report
.venv/bin/python intelligence/app/ais/cleaning.py --json /tmp/cleaning.json --out-cleaned /tmp/clean.csv
.venv/bin/python intelligence/app/ais/trajectory.py               # build trajectories + report
.venv/bin/python intelligence/app/ais/trajectory.py --json /tmp/trajectories.json
.venv/bin/python -m unittest discover -s intelligence/tests -v    # 99 tests (Phases 2-4)

cd intelligence                                                    # `app` must be importable
../.venv/bin/python -m app.ais.cleaning
../.venv/bin/python -m app.ais.trajectory
uvicorn app.main:app --reload --port 8000                          # once Phase 13 adds main.py
```