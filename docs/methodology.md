# ABYSS — Methodology

Status: **Phase 1**. This document states the intended method and its limits **before** implementation
(Phases 3–12), so that every later claim stays inside these bounds.

## 1. What ABYSS answers

> Which vessels' recorded movement is **compatible** with the reconstructed origin and release window
> of an observed oil slick?

It does **not** answer "which vessel caused this spill". ABYSS produces ranked candidates with
traceable, inspectable reasons and explicit uncertainty. Candidate ranking does not establish legal
responsibility.

## 2. Evidence chain (each step traceable)

```
Satellite observation -> oil slick -> origin reconstruction -> release time window
   -> candidate vessels -> trajectory compatibility -> behaviour analysis
   -> AIS gap analysis -> evidence score -> candidate ranking
```

Every arrow is a recorded data transformation; every conclusion in the report links back to the
observation, the environmental field, or the specific AIS positions that produced it.

## 3. Observation stage (Phase 12)

* Input: SAR scene (or the bundled demo scene), acquisition geometry and time.
* Detection: identify dark-formation candidates and attach a **detection confidence**, plus a
  `lookAlikeWarning` when characteristics are ambiguous. Look-alikes considered explicitly: low-wind
  areas, natural/biogenic surface films, radar artefacts (noise/sidelobe effects) and sea-state
  variations.
* Characterisation: area, centroid, bounding box, perimeter, approximate length and width,
  orientation, and GeoJSON-compatible geometry.
* Demo mode uses a bundled, pre-computed polygon so results are reproducible.
* *Assumption:* a production system would need multi-sensor or in-situ confirmation. This prototype
  does not claim that every dark SAR region is oil.

## 4. Origin reconstruction / hindcast (Phase 11)

Simplified **backward particle drift**:

```
P(t - dt) = P(t) - [ V_current(P, t) + w * V_wind(P, t) ] * dt
```

* Particles are seeded around the observed slick (centroid plus boundary sampling) and integrated
  backwards across the candidate release window.
* `w` is the **windage coefficient**, configurable; its prototype default is fixed and recorded in
  Phase 11 and is **not** presented as a calibrated scientific constant.
* Explicit time-stepping with a configurable step; the environmental field is interpolated bilinearly
  at particle positions.
* Output is a **density field** converted into a probable origin region (density threshold / hull of
  the densest cluster), an uncertainty polygon, a release time window, and an origin-reconstruction
  confidence derived from ensemble spread.

Explicit limits: no Stokes drift or wave action, no vertical mixing, no emulsification, no weathering
or evaporation, no shoreline interaction, no turbulence closure. The output is an uncertainty region,
**never an exact origin point**.

## 5. AIS processing (Phases 3–8)

1. **Ingest/normalise** CSV: identifiers, coordinates, timestamps (UTC), SOG/COG/heading.
2. **Validate**: reject invalid coordinates (out of range, exact `0,0`), impossible speed for the time
   step, malformed timestamps and duplicate records. Every rejection is **logged with a reason and
   counted** (`cleaningStatistics`); nothing is dropped silently.
3. **Construct trajectories**: group by vessel identifier, sort chronologically, compute geodesic
   segment distances (great-circle, not planar Euclidean), durations, average and maximum speed,
   course changes, stop/slow periods, and the gap list.
4. **Filter candidates** in stages, each producing its own reasoning:
   * *spatial* — was the vessel inside, or within a configurable distance of, the origin uncertainty
     region?
   * *temporal* — could it have been there during the estimated release window?
   * *trajectory* — is travel through the origin region physically possible between its previous and
     next recorded positions, given implied speed?
   * *behaviour* — slowdown, loitering, sharp course change, route deviation, unexpected stop.
   * *AIS gap* — missing intervals, duration, positions before/after, and whether crossing the origin
     region during the gap would require a plausible speed.

**Critical constraint:** an AIS gap alone must never strongly increase suspicion. A gap becomes
relevant only when the implied movement is physically compatible with the reconstructed origin region
and release window. This is enforced in scoring (Phase 10) and verified by test cases D and E
(Phase 19).

## 6. Behavioural baseline (Phase 8)

Where a vessel has enough history, its event-period behaviour is compared with its **own** baseline
(median speed, speed variability, typical course-change rate, typical stop duration). Deviations are
reported as a **behavioural anomaly** score — a statistical deviation, not evidence of wrongdoing, and
never phrased as such in the UI or report.

## 7. Explainable scoring (Phase 10)

Prototype weights, **configurable and not scientifically validated**:

| Factor | Max | Rationale |
|---|---|---|
| Spatial compatibility | 35 | strongest single discriminator: was the vessel plausibly at the origin region? |
| Temporal compatibility | 25 | narrows release-window overlap |
| Trajectory compatibility | 20 | physical plausibility of movement through the region |
| Behaviour anomaly | 10 | supporting context; alone it can never rank a vessel highly |
| AIS gap relevance | 10 | only when physically compatible (see section 5) |
| **Total** | **100** | |

Every candidate response contains `factors{}` **and** plain-language `reasons[]`, plus a
**counterfactual comparison** explaining why a nearby vessel scored lower (for example: physically
close but outside the release window). This prevents a naive "nearest vessel wins" outcome, which test
case G verifies.

## 8. Confidence reporting (Phases 17–18)

Detection, origin reconstruction, AIS evidence and overall investigation confidence are **reported
separately** with their derivation. The overall value uses an explicit, stated combination rule (for
example minimum critical factor plus documented weighting), never an unexplained average.

## 9. Known limitations (must appear in every generated report)

1. Dark SAR formations include look-alikes; detection confidence is not ground truth.
2. The drift model is simplified and its coefficients are prototype values: the origin is an
   uncertainty region, not a point.
3. Release-window granularity is limited by environmental field resolution and the AIS reporting
   interval.
4. AIS coverage is incomplete by nature (gaps, delayed or missing transmissions, quality issues), and
   in demo mode the data is **synthetic**.
5. Behavioural anomalies have innocent explanations (weather, waiting, fishing activity, technical
   faults, route constraints).
6. AIS transmission gaps can result from coverage, equipment or configuration issues, not only
   concealment.
7. Therefore the output is **investigation support**: ranked candidates with reasons, for a human
   investigator to verify against independent evidence.

## 10. Reproducibility

The demo dataset and every demo-mode computation are deterministic (fixed seeds, bundled inputs, no
network calls), so the same case always produces the same ranking and the same numbers during a
presentation. Re-running any phase must not change results.