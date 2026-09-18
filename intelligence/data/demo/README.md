# intelligence/data/demo — CASE-001 demonstration bundle

Everything in this directory is **committed**, **deterministic** and **synthetic**. It is what makes
DEMO MODE work with no API keys and no network access.

| File | Phase | Contents |
|---|---|---|
| `case_001.json` | 2 | case definition: id, study area, observation time, candidate release window |
| `demo_slick.json` | 2/12 | observed slick polygon (GeoJSON), centroid, detection confidence, look-alike flag |
| `demo_origin_expected.json` | 2 | the hindcast ground truth used **only to sanity-check the model in tests**, never shown as an answer to the user |
| `environmental/` | 2/11 | deterministic current + wind grids for the study area |
| `expected_ranking.json` | 2 | expected ordering properties (V001/V002 top, V004 not first, …) consumed by Phase 19 tests |

Rules:

1. No `datetime.now()`, no random generation without a fixed seed — regenerating must reproduce the
   same bytes.
2. Demo assets are always labelled `DEMO DATA` in the UI; AIS is always labelled
   `AIS: Synthetic Demonstration Dataset`.
3. `demo_origin_expected.json` is a **test fixture**, not evidence: the user-facing origin is always the
   model's uncertainty region with its confidence.
4. Vessel identities are invented and must not be traceable to real vessels.
