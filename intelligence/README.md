# intelligence/ — ABYSS FastAPI intelligence service

Python 3.11+ · FastAPI · NumPy · Pandas · SciPy · Shapely · GeoPandas (only if needed). Internal
service; the browser never calls it directly.

```
intelligence/
├── requirements.txt                 (Phase 2)
├── app/
│   ├── main.py                      FastAPI app + routers             (Phases 3–12)
│   ├── config.py                    env-driven settings + validation   (Phase 2)
│   ├── detection/                   SAR slick detection + look-alikes  (Phase 12)
│   ├── hindcast/                    backward particle drift model      (Phase 11)
│   ├── ais/                         cleaning, trajectories, spatial/temporal/trajectory
│   │                                filtering, gap analysis            (Phases 3–9)
│   ├── behaviour/                   baseline comparison, anomalies     (Phase 8)
│   ├── scoring/                     configurable weights, reasons, counterfactuals (Phase 10)
│   ├── providers/                   Satellite/Environmental/AIS provider abstractions
│   │                                + Demo* implementations            (Phase 2+)
│   └── schemas/                     Pydantic request/response models = the contract
├── data/
│   ├── satellite/                   demo scene + README (raw downloads ignored)
│   ├── environmental/               demo field + README
│   ├── ais/                         demo_ais_positions.csv (committed, synthetic)
│   └── demo/                        demo case bundle: slick, origin, window, expected ranking
└── tests/                           forensic test cases A–G + determinism tests (Phase 19)
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

## Commands (once Phase 2 adds `requirements.txt`)

```bash
python3 -m pip install -r requirements.txt      # or inside the virtualenv
uvicorn app.main:app --reload --port 8000
curl http://localhost:8000/health
pytest tests/ -v
```