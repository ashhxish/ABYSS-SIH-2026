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
not contain. Results on the synthetic CASE-001 extract: **3,710 rows in → 3,701 records, 9 rejected
(4 duplicate / 2 malformed timestamp / 2 invalid coordinate / 1 impossible speed), 1 value removed,
4 rows flagged**, all predicted by the Phase 2 defect inventory before the code was written.

## Commands

```bash
# from the repository root (all Python commands need the project virtual environment)
.venv/bin/python intelligence/app/ais/cleaning.py                 # clean the demo extract + report
.venv/bin/python intelligence/app/ais/cleaning.py --json /tmp/cleaning.json --out-cleaned /tmp/clean.csv
.venv/bin/python -m unittest discover -s intelligence/tests -v    # 77 tests (Phases 2-3)

cd intelligence                                                    # `app` must be importable
../.venv/bin/python -m app.ais.cleaning
uvicorn app.main:app --reload --port 8000                          # once Phase 13 adds main.py
```