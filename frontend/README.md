# frontend/ — ABYSS dashboard

React + Vite + React-Leaflet + Recharts. **Phase 15.** Not yet scaffolded: the scaffolding is created
in Phase 15 with `npm create vite` so that dependency versions are resolved and verified against the
Node.js actually installed on this machine (Node/npm are currently **absent**, see the root README).

## Planned structure

```
frontend/
├── index.html                 (Phase 15)
├── package.json               (Phase 15 — created by the Vite scaffold, then trimmed)
├── vite.config.js             (Phase 15)
├── public/                    static assets, favicon
└── src/
    ├── main.jsx, App.jsx      (Phase 15)
    ├── components/            shared UI: ConfidenceBadge, EvidenceCard, ScoreBreakdown,
    │                          DemoDataBanner, DisclaimerBanner, DataModeIndicator
    ├── pages/                 InvestigationOverview, SatelliteDetection, OriginReconstruction,
    │                          AisVesselInvestigation, CandidateRanking, VesselDetail,
    │                          ForensicTimeline, EvidenceChain, InvestigationReport
    ├── maps/                  Leaflet map + layer components: SatelliteFootprintLayer,
    │                          SlickLayer, SlickBoundaryLayer, OriginRegionLayer,
    │                          HindcastParticleLayer, VesselTrackLayer, CandidateTrackLayer,
    │                          AisGapLayer, EnvironmentalVectorLayer
    ├── charts/                Recharts: FactorBarChart, ScoreComparison, ConfidenceGauge,
    │                          SpeedProfileChart
    ├── services/              apiClient.js (talks only to the Spring Boot backend),
    │                          caseService.js, vesselService.js, reportService.js
    └└── data/                  demo fallbacks so the UI can be developed offline
```

## Rules for this module

1. The browser calls **the Spring Boot backend only** (`VITE_ABYSS_API_BASE_URL`) — never the Python
   service directly.
2. Every view that renders demo-mode data shows the `DEMO DATA` badge, and every AIS view shows
   `AIS: Synthetic Demonstration Dataset`.
3. The disclaimer is always visible where candidate rankings appear:
   *"ABYSS provides analytical evidence for investigation support. Candidate ranking does not establish
   legal responsibility."*
4. Confidence values (detection, origin, AIS evidence, overall) are displayed separately, never merged.
5. Dark maritime-intelligence visual language: map-centric, restrained colours, no decorative
   animation.
6. No secrets in the frontend: only `VITE_`-prefixed variables are ever placed in the bundle, and no
   provider credential is ever exposed to the browser.

## Commands (once Phase 15 has run)

```bash
npm install
npm run dev      # http://localhost:5173
npm run build
```