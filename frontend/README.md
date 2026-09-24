# frontend/ — ABYSS Intelligence Console

React 18 + Vite 5 dashboard for the Phase 13 intelligence API. **Phase 15 investigation experience.**
No Spring Boot, no PostgreSQL, no authentication, no external API keys, no map
tiles. Every number on screen comes from the real `/investigate`, `/detect`,
`/ais/clean` and `/ais/trajectory` responses — the UI invents no demo data.

## Run the demo (two terminals)

```bash
# Terminal 1 — Phase 13 intelligence service
cd /home/ashish/SIH/SIH_Prototypr/ABYSS/intelligence
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — this frontend
cd /home/ashish/SIH/SIH_Prototypr/ABYSS/frontend
npm install
npm run dev
```

Open **http://localhost:5173/**. The dev server proxies `/api` → `http://127.0.0.1:8000`,
so the browser stays on one origin (no CORS setup) and no backend host is baked
into the bundle. Point the proxy elsewhere with
`VITE_API_PROXY_TARGET=http://host:port npm run dev`.

## Other commands

| Command | What it does |
|---|---|
| `npm run dev` | Vite dev server with the `/api` proxy (port 5173) |
| `npm run build` | Production bundle into `dist/` |
| `npm run preview` | Serve the built bundle (port 4173) |
| `npm test` | Unit tests for the pure projection/formatting helpers (Node's built-in runner, no extra deps) |

For a production build, set the API base at build time:
`VITE_API_BASE_URL=https://your-host/api npm run build`.

## Structure

```
frontend/
├── index.html
├── vite.config.js             dev proxy /api -> intelligence service
├── tests/                     node --test suites (geo projection, formatting)
└── src/
    ├── main.jsx, App.jsx      shell: loads the case, owns selection + error states
    ├── api.js                 fetch wrapper: timeouts, aborts, ApiError with status
    ├── styles.css             all styling (no CSS framework)
    ├── lib/
    │   ├── format.js          number/date/duration formatting, factor flattening
    │   └── geo.js             equirectangular projection + SVG path builders
    └── components/
        ├── Header.jsx         case identity, data source, synthetic-data banner
        ├── Workflow.jsx       the 5-step investigation workflow (status per step)
        ├── ObservationCard.jsx  step 1-2: satellite detection + look-alike screening
        ├── OriginCard.jsx     step 3: release region, window, drift model
        ├── ConfidencePanel.jsx investigation confidence + stated limitations
        ├── MapPanel.jsx       SVG plot: slick, origin region, backdrift, AIS track
        ├── AisPanel.jsx       step 4: cleaning audit, trajectory totals, screening
        ├── CandidateTable.jsx step 5: ranked vessels with factor mini-bars
        ├── CandidateDetail.jsx per-vessel evidence, reasons, counterfactual, track
        └── ui.jsx             Card/Row/Badge/Stat/Bar/Gauge/Notice primitives
```

## Notes

- `src/components/{pages,maps,charts,services,data}/` from the original plan are
  intentionally unused. The console is one page with one flow, and the map is
  drawn locally so the demo needs no tile server or API key.
- The map is a schematic equirectangular plot (no basemap) — see the legend in
  the UI. It is not for navigation.
- The `/ais/trajectory` bundle is ~2 MB, so it is fetched after the core case
  renders; every panel shows its own loading/error state independently.
