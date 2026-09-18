# intelligence/data/demo — demonstration bundles

**Committed, deterministic, synthetic.** This directory is what makes DEMO MODE work with no API keys
and no network access.

## Contents

| Path | Phase | Status |
|---|---|---|
| `generate_case_001.py` | 2 | ✅ the generator for the CASE-001 dataset (stdlib only, no dependencies) |
| `case_001/` | 2 | ✅ **the generated dataset** — see `case_001/README.md` for the full description |
| `case_001/README.md` | 2 | ✅ what each vessel represents, which are candidates, which are distractors, which anomalies are intentional |

Later phases add their own bundles here (for example a satellite scene manifest), always prefixed so
they are not confused with real data.

## Rules

1. The generator must be runnable with **only the Python standard library**, so the demo can be
   regenerated before a presentation on any machine.
2. No `datetime.now()`, no unseeded randomness: `case_001/` is byte-reproducible (verified by
   `intelligence/tests/test_case_001_dataset.py`).
3. Demo assets are always labelled `DEMO DATA`; AIS is always labelled
   `AIS: Synthetic Demonstration Dataset`.
4. `case_001/demo_origin_expected.json` is a **test fixture (answer key)**. It is never an input to
   the analysis pipeline and must never be surfaced by the API, the dashboard or a report.
5. Vessel identities are synthetic and must not be traceable to real vessels.

## Regenerate

```bash
python3 intelligence/data/demo/generate_case_001.py     # in place
python3 -m unittest discover -s intelligence/tests      # verify it still matches
```
