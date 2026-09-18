# ABYSS — Demo scenario (CASE-001)

Status: **Phase 1 design contract**. The data itself is generated in **Phase 2**; this document fixes
what that data must contain so the scoring engine is genuinely tested. Everything here is
**synthetic** and must be labelled as such in the UI and in every report.

## 1. Purpose

Demonstrate the full forensic story end to end, offline, deterministically:

> Satellite imagery detects an oil slick → the observed slick position is not the release position →
> ABYSS reconstructs the probable origin and a release time window → historical AIS is filtered
> against that region and window → candidates are analysed by trajectory, behaviour and gap evidence →
> an explainable candidate ranking is produced → investigators can inspect exactly why each vessel was
> ranked.

## 2. Scenario outline

| Element | Design value (to be generated in Phase 2) |
|---|---|
| Case ID | `CASE-001` |
| Study area | a bounded offshore region with a synthetic coastline used for plausibility checks |
| Observation | one SAR acquisition timestamp; footprint covering the study area |
| Observed slick | one bounded polygon, a few tens of km², elongated along the current/wind-driven axis |
| Release window | a multi-hour window **earlier** than the observation time (drift takes time) |
| Origin region | located up-current/up-wind of the observed slick; the true release cell lies inside the region but is **never** published as a point |
| Vessels | 12 synthetic vessels, 48–72 h of positions, reporting interval 1–10 min |
| Environmental field | analytic, deterministic current + wind field (fixed formula, no run-to-run randomness) |

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

## 4. Data quality fixtures (Phase 3 target)

The demo CSV intentionally contains realistic defects so cleaning is demonstrable and testable:

* duplicate rows (identical MMSI + timestamp);
* a malformed timestamp string;
* out-of-range coordinates and at least one `(0, 0)` position;
* one impossible speed (a jump implying an unphysical velocity for the interval);
* a vessel with a missing optional field (heading or navigation status).

Cleaning must **report** counts and reasons for every rejected row (`cleaningStatistics`) and never
drop rows silently.

## 5. Determinism requirements

* Fixed random seed; no `datetime.now()` inside data generation; all timestamps derive from fixed
  constants.
* Generated files are committed (`intelligence/data/ais/demo_ais_positions.csv`,
  `intelligence/data/demo/*.json`) so the demo never depends on regeneration.
* Re-running any analysis phase returns identical numbers — asserted in Phase 19.
* No network access is required or attempted in demo mode.

## 6. Public demonstration summary (what the presenter says)

> "This slick was observed here, but oil drifts — so its release point is somewhere else. ABYSS
> reconstructs a probable origin region and a release window from currents and wind, then asks which
> vessels' recorded movement is compatible with that reconstruction. V001 and V002 are the strongest
> candidates; V002's AIS gap matters **because** it is physically consistent with the region, while
> V003's similar gap does not. The vessel nearest to the slick, V004, does not rank first — and every
> score is broken down into observable reasons with uncertainty."

Nothing in the demo claims that a specific vessel caused the spill.

## 7. Labelling (non-negotiable)

| Surface | Required label |
|---|---|
| Any map or table showing AIS | `AIS: Synthetic Demonstration Dataset` |
| Environmental values from the bundle | `DEMO DATA` |
| Detection / scenario results | `DEMO DATA` |
| Report | synthetic-data notice plus the investigation-support disclaimer |