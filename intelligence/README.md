# intelligence/ — ABYSS FastAPI intelligence service

Python 3.11+ · FastAPI · NumPy · Pandas · SciPy · Shapely · GeoPandas (only if needed). Internal
service; the browser never calls it directly.

```
intelligence/
├── requirements.txt                 (Phase 3: pandas, numpy — pinned to installed versions)
├── app/
│   ├── __init__.py
│   ├── config.py                    env-driven settings + startup validation   (Phase 3 ✅)
│   ├── geo.py                       shared geodesy helpers                     (Phase 3 ✅)
│   ├── timeutils.py                 one UTC parser + ReleaseWindow             (Phases 5-11 ✅)
│   ├── investigation.py             evidence pipeline orchestrator   (Phases 5-11 assembled ✅)
│   ├── main.py                      FastAPI app + routers             (Phases 12-13)
│   ├── detection/                   SAR slick detection + look-alikes  (Phase 12)
│   ├── hindcast/
│   │   ├── environmental.py         gridded current/wind field + bilinear lookup (Phase 11 ✅)
│   │   └── origin.py                backward particle drift -> origin REGION (Phase 11 ✅)
│   ├── ais/
│   │   ├── __init__.py
│   │   ├── cleaning.py              ingestion, validation, audit trail   (Phase 3 ✅)
│   │   ├── trajectory.py            ordered tracks, legs, gaps, events    (Phase 4 ✅)
│   │   ├── filtering.py             spatial / temporal / trajectory compatibility (Phases 5-7 ✅)
│   │   └── gap_analysis.py          gap feasibility x relevance            (Phase 9 ✅)
│   ├── behaviour/                   own-baseline comparison, gated anomalies (Phase 8 ✅)
│   ├── scoring/                     configurable weights, reasons, counterfactuals (Phase 10 ✅)
│   ├── providers/                   provider abstractions + Demo* implementations (planned:
│   │                                demo labelling currently lives in the Phase 3 loader)
│   └── schemas/                     Pydantic models = the service contract (Phase 13)
├── data/
│   ├── satellite/                   demo scene + README (raw downloads ignored)
│   ├── environmental/               README; the demo field ships inside the case bundle
│   ├── ais/                         README: where AIS datasets live (demo extract is inside the
│   │                                case bundle at data/demo/case_001/ais/)
│   └── demo/
│       ├── generate_case_001.py     deterministic dataset generator    (Phase 2 ✅)
│       └── case_001/                the generated CASE-001 bundle      (Phase 2 ✅)
└── tests/                           253 tests: dataset (Phase 2), cleaning (3), trajectory (4),
                                     compatibility (5-7), behaviour (8), gaps (9), scoring (10),
                                     hindcast (11) and end-to-end pipeline
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

## Evidence pipeline (Phases 5-11 — implemented)

`app/investigation.py` assembles the whole chain and returns one explainable result:

```
cleaning (3) -> trajectories (4) -> origin hindcast (11)
   -> compatibility (5-7) -> behaviour (8) -> gaps (9) -> scoring + ranking (10)
```

| Module | Question it answers | Reported as |
|---|---|---|
| `ais/filtering.py` | How close was it, and was it inside the region **while the window was open**? | distances in km, `insideRegionRelation`, in-region presence seconds, physical plausibility of in-window motion |
| `behaviour/baseline.py` | Does its behaviour differ from **its own** track-wide baseline? | raw anomaly 0-1 from four named components, plus a gated `scoredAnomaly` |
| `ais/gap_analysis.py` | Could it have crossed the region while silent, and does the gap matter? | per-gap feasibility, relevance 0-1, `bestEvidenceValue` |
| `scoring/engine.py` + `ranking.py` | What evidence exists, and in what order? | per-factor points **and** a plain-language reason per factor, counterfactuals, tie groups |

Measured on CASE-001 (default weights: spatial 35 · temporal 25 · trajectory 20 · behaviour 10 ·
gap 10):

| | |
|---|---|
| Origin region | 119.5 km² hull, spread 6.8 km, confidence 0.77; release window `2026-03-13T10:00Z → 18:00Z` |
| Inside the region during the window | **3 vessels** — V001, V002, V003 (matches the generator's declared intent) |
| Ranking | V001 **83.564** · V002 **83.200** · V003 **80.125** · nine vessels tied at **0.000** |
| Gap factor | V002 **3.0/10** (the full 30 % cap, feasible at 10.5 kn) vs V003 **0/10** (35.1 kn required) |
| Behaviour | 4 anomalies reported; only V001's is flagged **and** inside the region (raw 0.36 → **3.564/10**). V006's 0.35 stays context (outside, 0 points); V002/V003's sub-threshold anomalies contribute 0.20 and 0.13 |
| Spatial falloff | 30 km: V005 is 108 km away during the window, so no "nearest vessel" credit |
| Nearest vessel to the slick | V004 is **1.1 km** from the slick ring at its record nearest the observation time, yet ranks **4th with 0.000** — the rank-1 counterfactual says why |

The nine equal scores are deliberate and surfaced as a `tieGroups` entry: they are vessels with no
evidence of any kind, and the ordering inside that group is an identifier tie-break explicitly labelled
"deterministic, not evidential". The test suite asserts that behaviour rather than hiding it.

## Commands

```bash
# from the repository root (all Python commands need the project virtual environment)
.venv/bin/python intelligence/app/ais/cleaning.py                 # clean the demo extract + report
.venv/bin/python intelligence/app/ais/cleaning.py --json /tmp/cleaning.json --out-cleaned /tmp/clean.csv
.venv/bin/python intelligence/app/ais/trajectory.py               # build trajectories + report
.venv/bin/python intelligence/app/ais/trajectory.py --json /tmp/trajectories.json
.venv/bin/python -m unittest discover -s intelligence/tests -v    # 253 tests (Phases 2-11)

cd intelligence                                                    # `app` must be importable
../.venv/bin/python -m app.ais.cleaning
../.venv/bin/python -m app.ais.trajectory
../.venv/bin/python -m app.investigation                           # full pipeline, printed ranking
../.venv/bin/python -m app.investigation --json /tmp/investigation.json
../.venv/bin/python -m app.investigation --weight-gap 100 --weight-spatial 0 \
    --weight-trajectory 0 --weight-behaviour 0 --weight-temporal 0  # re-weighted run
uvicorn app.main:app --reload --port 8000                          # once Phase 13 adds main.py
```