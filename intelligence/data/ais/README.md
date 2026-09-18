# intelligence/data/ais — AIS datasets

| File | Committed | Description |
|---|---|---|
| `README.md` | yes | this file |
| `demo/case_001/ais/demo_ais_positions.csv` | **yes** (Phase 2) | **synthetic** demonstration AIS positions for `CASE-001` — see `../../demo/case_001/README.md` |
| anything else | no | real/licensed AIS extracts — never committed |

The synthetic demo extract lives with its case bundle under `intelligence/data/demo/case_001/ais/`
so that a case's inputs travel together. The file is committed; everything else under
`intelligence/data/` is git-ignored, so a licensed real-world AIS extract cannot be committed by
accident.

## Actual columns of the demo extract (Phase 2)

```
MMSI, IMO, vesselName, vesselType, timestamp, latitude, longitude, SOG, COG, heading, navigationStatus, datasetLabel
```

| Column | Notes |
|---|---|
| `MMSI`, `IMO` | synthetic placeholders (`9000000NN`, `9990xxC` with a valid IMO check digit) |
| `timestamp` | ISO-8601 UTC, e.g. `2026-03-14T06:00:00Z`. **Two rows carry deliberately malformed timestamps** as Phase 3 cleaning fixtures |
| `latitude`, `longitude` | decimal degrees. **Two rows carry deliberately invalid coordinates** (`(0,0)` and latitude `95.2`) |
| `SOG` | knots; one row is deliberately negative; one row is part of an impossible speed jump |
| `COG`, `heading` | degrees (COG 0.0–359.9, heading integer 0–359); three rows omit these optional fields |
| `navigationStatus` | optional AIS navigational status |
| `datasetLabel` | `Synthetic Demonstration Dataset` on every row |

Units and conventions are documented here and in `docs/data-sources.md`; the loader (Phase 3) must not
assume anything not stated here.

## Warning

**The demo file is synthetic.** Its MMSI/IMO values and vessel names are invented for the prototype
and must not be traceable to real vessels. Any UI or report that displays it must state
`AIS: Synthetic Demonstration Dataset`. Synthetic AIS is never presented as real-world evidence.