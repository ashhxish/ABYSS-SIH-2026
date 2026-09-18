# intelligence/data/ais — AIS datasets

Contents of this directory:

| File | Committed | Description |
|---|---|---|
| `README.md` | yes | this file |
| `demo_ais_positions.csv` | **yes** (Phase 2) | **synthetic** demonstration AIS positions for `CASE-001` |
| any other `*.csv` | no | real/licensed AIS extracts — never committed |

Everything under `intelligence/data/` other than files starting with `demo_` is git-ignored, so a
licensed real-world AIS extract cannot be committed by accident.

## Required columns (Phase 3 loader)

```
MMSI, IMO, vesselName, vesselType, timestamp, latitude, longitude, SOG, COG, heading, navigationStatus
```

* `timestamp` — ISO-8601 in UTC (for example `2026-03-14T02:30:00Z`).
* `SOG` — speed over ground in knots; `COG`/`heading` in degrees.
* Units and conventions are documented here rather than assumed.

## Warning

**The demo file is synthetic.** Its MMSI/IMO values and vessel names are invented for the prototype
and must not be traceable to real vessels. Any UI or report that displays it must state
`AIS: Synthetic Demonstration Dataset`. Synthetic AIS is never presented as real-world evidence.