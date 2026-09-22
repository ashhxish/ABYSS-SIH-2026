# ABYSS — Demo scenario (CASE-001)

Status: **Phase 2 complete** — the dataset exists at `intelligence/data/demo/case_001/`, and its
authoritative description (per-vessel roles, measured numbers, injected defects) is
`intelligence/data/demo/case_001/README.md`. This document records the design contract that the
generated data implements. Everything here is **synthetic** and must be labelled as such in the UI and
in every report.

## 1. Purpose

Demonstrate the full forensic story end to end, offline, deterministically:

> Satellite imagery detects an oil slick → the observed slick position is not the release position →
> ABYSS reconstructs the probable origin and a release time window → historical AIS is filtered
> against that region and window → candidates are analysed by trajectory, behaviour and gap evidence →
> an explainable candidate ranking is produced → investigators can inspect exactly why each vessel was
> ranked.

## 2. Scenario outline

| Element | Value in the generated dataset |
|---|---|
| Case ID | `CASE-001` |
| Study area | bounded offshore box lat 16.5–20.0, lon 69.5–74.5, with a synthetic coastline polyline for plausibility checks |
| Observation | one synthetic SAR stand-in at `2026-03-14T06:00:00Z`, footprint covering the study area |
| Observed slick | one polygon, 41.4 km², ~12 km × 4.4 km, oriented ~52°, centroid 18.4663 N / 72.1631 E |
| Release window | `2026-03-13T10:00:00Z` → `18:00:00Z` (before the observation, because drift takes time) |
| Origin region | ellipse 10 km × 6 km at bearing 50° centred on the fixture release point 18.3000 N / 71.9000 E; the release point lies inside but is **never** published as a point |
| Observed ≠ released | slick centroid is **33.4 km** downstream of the release point (bearing ~56°) |
| Vessels | 12 synthetic vessels, 72 h of records, 3,675 rows, reporting interval 5 min (candidates) / 10 min (controls) |
| Environmental field | analytic deterministic current + wind field: wind 8 m/s from 225°, current 0.32/0.20 m/s, windage 0.03 |

The oil is deliberately **not** at the release position: the same coordinates are never shared, so any
"nearest vessel to the slick" shortcut produces a visibly wrong ranking. That is the core teaching
point of the demo.

## 3. Vessel roles (each role maps to a specification test case)

| ID | Role | Expected behaviour | Verified by |
|---|---|---|---|
| V001 | **Primary plausible candidate** | inside the origin region during the release window; trajectory compatible; moderate slowdown near the region | Case A (high compatibility) |
| V002 | **Gap-compatible candidate** | AIS gap overlapping the release window; distance traversable at plausible speed; endpoints bracket the region | Case E (gap becomes relevant) |
| V003 | **Gap-impossible candidate** | similar gap, but the distance between last and first position is far beyond plausible speed | Case D (gap contributes little) |
| V004 | **Misleading neighbour** | physically closest to the **observed slick** at observation time, but nowhere near the origin region during the release window | Cases C and G (nearest ≠ top-ranked) |
| V005 | **Wrong-time candidate** | crosses the origin region, but hours **after** the release window closes | Case B (low temporal score) |
| V006 | **Anomalous but remote** | strong speed anomaly and erratic course changes, but > 150 km from the origin region | Case F (anomaly alone cannot rank highly) |
| V007 | **Tanker on a legitimate route** | steady speed and course, sufficient distance from the region; control case | sanity: mid/low score, no behaviour flags |
| V008 | **Fishing-like vessel** | slow, looping tracks, frequent stops (legitimate behaviour that must not be labelled suspicious by itself) | sanity: low spatial score despite many slow periods |
| V009 | **Ferry / liner** | high steady speed along a straight corridor outside the region | sanity: high speed is not suspicious by itself |
| V010 | **Coasting vessel near shore** | plausible proximity but a shoreline-consistent track | sanity: trajectory plausibility check |
| V011 | **Tug / support vessel** | short local movement with port stops | sanity: stop periods must not be over-weighted |
| V012 | **Far offshore transiting vessel** | minimal relevance; inclusion proves filtering removes noise | sanity: filtered out early |

Expected outcome: V001 and V002 rank highest; V003 ranks clearly lower than V002 despite a similar
gap; V004 must **not** be first; V006 must stay out of the top ranks.

## 4. Data quality fixtures (Phase 3 targets)

The generated CSV contains **13 intentionally defective rows** so that cleaning is demonstrable and
testable — and so that "cleaning" cannot be implemented as "delete anything awkward silently":

| Category | Rows | Vessel | Detail |
|---|---|---|---|
| `duplicate_record` | 4 | V007 | exact duplicates (MMSI, timestamp, position, SOG, COG all identical) |
| `malformed_timestamp` | 2 | V008 | `2026-03-12T25:61:00Z` (invalid fields) and `12/03/2026 08:00` (non-ISO) |
| `invalid_coordinate` | 2 | V010, V012 | null-island `(0, 0)` and latitude `95.2` |
| `negative_speed` | 1 | V006 | `SOG = -3.0` |
| `impossible_speed_jump` | 1 | V006 | one record 60 km from its neighbour 5 minutes later (~720 km/h); teleports out and back, so it yields **two** impossible consecutive steps from that single row |
| `missing_optional_field` | 3 | V011 | `heading` and `navigationStatus` blank; row otherwise valid |

Every fixture is inventoried in `case_001.json` → `injectedDefects` with a stable `defectId`, the
identifying values and an `expectedPhase3Action`, and each malformed-timestamp row keeps its intended
position in the file's timestamp ordering. Cleaning must **report** counts and reasons per category
(`cleaningStatistics`) and never drop rows silently.

## 5. Intentional AIS transmission gaps

| Vessel | Gap | Bridge | Implied speed | Expected treatment |
|---|---|---|---|---|
| V002 | 11:55Z → 16:00Z (4.08 h between the records either side of the outage), starting inside the origin region, spanning it | 79.4 km | **10.5 kn** | feasible → the gap is *relevant*, but remains weak evidence |
| V003 | identical timing and starting point | 265.8 km | **35.1 kn** | impossible → the gap must contribute almost nothing |

V002 and V003 exist as a matched pair: same place, same window, same gap length. Only physical
feasibility differs, which isolates the constraint that *an AIS gap alone must never strongly increase
suspicion*.

## 6. Determinism requirements

* No `datetime.now()`, no unseeded randomness: all timestamps derive from fixed constants.
* Generated files are committed under `intelligence/data/demo/case_001/`, so the demo never depends on
  regeneration, and `manifest.json` carries a SHA-256 for each file.
* A fresh run reproduces the committed bytes exactly; `intelligence/tests/test_case_001_dataset.py`
  (35 tests) asserts this, alongside the scenario properties and every injected defect.
* The generator itself runs 51 design self-checks and refuses to write output if the scenario loses one
  of its documented properties.
* No network access is required or attempted in demo mode.

## 7. Public demonstration summary (what the presenter says)

> "This slick was observed here, but oil drifts — so its release point is somewhere else. ABYSS
> reconstructs a probable origin region and a release window from currents and wind, then asks which
> vessels' recorded movement is compatible with that reconstruction. V001 and V002 are the strongest
> candidates; V002's AIS gap matters **because** it is physically consistent with the region, while
> V003's similar gap does not. The vessel nearest to the slick, V004, does not rank first — and every
> score is broken down into observable reasons with uncertainty."

Nothing in the demo claims that a specific vessel caused the spill.

## 8. Labelling (non-negotiable)

| Surface | Required label |
|---|---|
| Any map or table showing AIS | `AIS: Synthetic Demonstration Dataset` |
| Environmental values from the bundle | `DEMO DATA` |
| Detection / scenario results | `DEMO DATA` |
| Report | synthetic-data notice plus the investigation-support disclaimer |