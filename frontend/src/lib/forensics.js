/**
 * Phase 23 - uncertainty-aware maritime forensic assessment.
 *
 * This module turns the evidence ABYSS already has into four investigator-facing
 * judgements, and nothing more:
 *
 *   1. an evidence SUFFICIENCY band for one candidate;
 *   2. the uncertainty cascade from observation to investigation confidence;
 *   3. the competing hypotheses the available data can and cannot discriminate;
 *   4. the next evidence worth acquiring.
 *
 * Three rules govern everything here, and they are the reason this file exists
 * as a pure module rather than inline JSX:
 *
 *   - NO FABRICATION. Every number is either read from an existing API field or
 *     is an explicit arithmetic combination of API fields (the `composite` and
 *     `aisCoverage` derivations below say which fields, and how). A dimension the
 *     API did not supply stays `null` and renders as "Not available". The module
 *     never invents a confidence, an accuracy, a probability or a radius.
 *   - NO ATTRIBUTION. Nothing produced here is a probability of responsibility
 *     or a legal conclusion. Bands are named "EVIDENCE COMPATIBILITY" and the
 *     ordering they feed is called investigation priority.
 *   - PROVENANCE ALWAYS. Every node carries the API path it was derived from, in
 *     the same `detection.*` / `origin.*` / `ranking[]...` convention the
 *     evidence chain already uses, so the console stays auditable.
 *
 * Thresholds and weights are declared once, in `SUFFICIENCY_THRESHOLDS` and
 * `SUFFICIENCY_WEIGHTS`, so they can be tuned without touching component code.
 */

import { factorRows, rankingEntries, findCandidate, clamp } from './format.js'
import { EVIDENCE_STATUS, numberOrNull, confidencePercent } from './timeline.js'
import { boundsOf, normalisePoints, ringToLatLon } from './geo.js'

/* ------------------------------------------------------------------ tuning */

/**
 * Every tunable number in the sufficiency model. These are prototype choices,
 * not physical constants - exactly like the scoring engine's own thresholds,
 * which the API reports in `ranking[].compatibility.notes`.
 */
export const SUFFICIENCY_THRESHOLDS = Object.freeze({
  /** Composite >= this, with few contradictions, reads as HIGH compatibility. */
  high: 70,
  /** Composite >= this reads as MODERATE compatibility; below it, INSUFFICIENT. */
  moderate: 45,
  /** More contradicting factors than this blocks the HIGH band. */
  maxContradictionsForHigh: 1,
  /** Origin confidence below this is surfaced as an explicit caution. */
  originCautionBelow: 80,
  /** AIS window coverage below this percent is surfaced as an explicit caution. */
  aisCoverageCautionBelow: 95,
  /** A dimension at or above this percent can be listed as supporting evidence. */
  supportingDimensionPercent: 70,
})

/**
 * Relative weight of each sufficiency dimension.
 *
 * The five candidate dimensions inherit the spirit of the scoring engine's own
 * weights (spatial and temporal dominate); detection/origin/AIS coverage are
 * observation-quality weights. They sum to 100, and the composite is
 * re-normalised over whatever subset is actually available, so a missing
 * dimension cannot silently deflate a case.
 */
export const SUFFICIENCY_WEIGHTS = Object.freeze({
  detection: 10,
  origin: 15,
  spatial: 20,
  temporal: 20,
  trajectory: 15,
  behaviour: 5,
  aisCoverage: 10,
  gap: 5,
})

/** The three bands the brief names, verbatim. */
export const SUFFICIENCY = Object.freeze({
  HIGH: 'HIGH EVIDENCE COMPATIBILITY',
  MODERATE: 'MODERATE EVIDENCE COMPATIBILITY',
  INSUFFICIENT: 'INSUFFICIENT EVIDENCE',
})

/** Badge tone for each band, using the console's existing tone vocabulary. */
export const SUFFICIENCY_TONE = Object.freeze({
  [SUFFICIENCY.HIGH]: 'ok',
  [SUFFICIENCY.MODERATE]: 'warn',
  [SUFFICIENCY.INSUFFICIENT]: 'danger',
})

/** Status vocabulary for competing hypotheses. */
export const HYPOTHESIS_STATUS = Object.freeze({
  SUPPORTED: 'SUPPORTED BY AVAILABLE EVIDENCE',
  PARTIAL: 'PARTIALLY SUPPORTED',
  WEAK: 'WEAK / UNRESOLVED',
  NO_DATA: 'INSUFFICIENT DATA',
})

export const HYPOTHESIS_TONE = Object.freeze({
  [HYPOTHESIS_STATUS.SUPPORTED]: 'ok',
  [HYPOTHESIS_STATUS.PARTIAL]: 'warn',
  [HYPOTHESIS_STATUS.WEAK]: 'low',
  [HYPOTHESIS_STATUS.NO_DATA]: 'neutral',
})

/**
 * The assessment's standing caveat, shown wherever a band is displayed. Kept
 * here so it cannot drift between the evidence stage and the review stage.
 */
export const ASSESSMENT_STANDING =
  'An investigation-priority assessment of how far the available evidence is mutually compatible. It is not a declaration that a vessel caused the spill, and it is not a legal standard.'

/* ----------------------------------------------------------------- helpers */

const clamp01 = (value) => clamp(Number(value), 0, 1)

/** 0-1 fraction -> whole percent, or null when the input was unusable. */
const pct = (value) => {
  const n = numberOrNull(value)
  return n == null ? null : Math.round(clamp01(n) * 100)
}

const round = (value, digits = 1) => {
  const n = numberOrNull(value)
  return n == null ? null : Number(n.toFixed(digits))
}

/**
 * Read a value and keep its provenance. `available` is false - never a
 * fabricated zero - when the API response carried nothing usable.
 */
function fact({ label, value, source, available = true, display = null, note = null }) {
  return {
    label,
    value: value === undefined ? null : value,
    display,
    available: available && value !== undefined && value !== null,
    unavailableReason: available && value !== undefined && value !== null ? null : 'Not provided by the API response.',
    source,
    note,
  }
}

/** A supporting/caution line: a statement plus the API path that justifies it. */
function point(label, source, detail = null) {
  return { label, source, detail }
}

/* ============================================================ FEATURE 1
 * Evidence sufficiency gate.
 * ====================================================================== */

/** One sufficiency dimension. `percent` is null when the API supplied nothing. */
function dimension({
  key,
  label,
  supportLabel,
  cautionLabel,
  percent,
  source,
  critical = false,
  role = 'evidence',
  detail = null,
  note = null,
}) {
  return {
    key,
    label,
    supportLabel,
    cautionLabel,
    percent,
    available: percent != null,
    critical,
    role,
    source,
    detail,
    note,
    weight: SUFFICIENCY_WEIGHTS[key] ?? null,
    display: percent == null ? 'Not available' : `${percent}%`,
  }
}

/**
 * AIS coverage of the release window, taken from the two API fields the engine
 * already reports deliberately separately (see `ranking[].compatibility.notes`):
 * `windowCoverageSeconds` is the time the window is covered by AIS records at
 * all, i.e. AIS availability.
 *
 * Returns null - never a guessed default - when either field is absent.
 */
export function aisCoveragePercent(compatibility, releaseWindow) {
  const covered = numberOrNull(compatibility?.windowCoverageSeconds)
  const hours = numberOrNull(releaseWindow?.durationHours)
  if (covered == null || hours == null || !(hours > 0)) return null
  return pct(covered / (hours * 3600))
}

/**
 * The factors that argue against this candidate, each with its source path.
 *
 * Deliberately NOT included: a missing AIS gap. The engine states that "the
 * ABSENCE of a gap is not evidence either", so the absence of a gap is never
 * counted against a candidate here. A gap only counts against a candidate when
 * the engine itself judged it physically infeasible.
 */
export function contradictingFactors(entry) {
  const out = []
  if (!entry) return out
  const filters = entry.compatibility?.filters || {}
  if (filters.spatial === false) {
    out.push(point('Not recorded inside the probable origin region during the release window', 'ranking[].compatibility.filters.spatial'))
  }
  if (filters.temporal === false) {
    out.push(point('Not present in the probable origin region while the release window was open', 'ranking[].compatibility.filters.temporal'))
  }
  if (filters.trajectory === false) {
    out.push(point('Recorded course changes do not plausibly reach the origin region', 'ranking[].compatibility.filters.trajectory'))
  }
  const behaviour = entry.behaviour || {}
  if (behaviour.isAnomaly === true && behaviour.scoredEligible === false) {
    out.push(point('Behavioural anomaly is context only: no presence in the region to correlate it with', 'ranking[].behaviour.scoredEligible'))
  }
  const gaps = entry.gapAnalysis || {}
  if (gaps.hasGap === true && gaps.anyFeasible === false) {
    out.push(point('Recorded AIS gap is not physically feasible at the implied speed', 'ranking[].gapAnalysis.anyFeasible'))
  }
  return out
}

/**
 * The eight dimensions the gate considers, each read from an existing field:
 * three case-level observation-quality dimensions (detection, origin, AIS
 * coverage) and the candidate's own five compatibility factors, passed through
 * from the engine unchanged via `factorRows`.
 */
export function sufficiencyDimensions({ investigation, detection, candidate } = {}) {
  const region = investigation?.origin?.region || {}
  const releaseWindow = investigation?.origin?.releaseWindow || {}
  const entry = candidate || null
  const compatibility = entry?.compatibility || {}
  const gapAnalysis = entry?.gapAnalysis || {}
  const factorByKey = Object.fromEntries(factorRows(entry?.factors).map((f) => [f.key, f]))
  const factorPercent = (key) => (entry ? pct(factorByKey[key]?.percent) : null)

  return [
    dimension({
      key: 'detection',
      label: 'Detection',
      supportLabel: 'Detection confidence',
      cautionLabel: 'Detection confidence is limited',
      percent: pct(detection?.detectionConfidence),
      source: 'detection.detectionConfidence',
      critical: true,
      detail: detection?.classification ?? null,
      note: detection?.detectionConfidenceNote ?? null,
    }),
    dimension({
      key: 'origin',
      label: 'Origin',
      supportLabel: 'Origin reconstruction',
      cautionLabel: 'Origin uncertainty',
      percent: pct(region.confidence),
      source: 'origin.region.confidence',
      critical: true,
      detail: numberOrNull(region.areaKm2) != null
        ? `${round(region.areaKm2, 1)} km² probable origin region`
        : null,
      note: 'Confidence reflects the internal spread of the prototype reconstruction, not scientific accuracy.',
    }),
    dimension({
      key: 'spatial',
      label: 'Spatial compatibility',
      supportLabel: 'Spatial compatibility',
      cautionLabel: 'Spatial compatibility is weak',
      percent: factorPercent('spatial'),
      source: 'ranking[].factors.spatial',
      detail: numberOrNull(compatibility.minDistanceKmDuringWindow) != null
        ? `Closest in-window approach ${round(compatibility.minDistanceKmDuringWindow, 1)} km to the probable origin region`
        : null,
    }),
    dimension({
      key: 'temporal',
      label: 'Temporal compatibility',
      supportLabel: 'Temporal compatibility',
      cautionLabel: 'Temporal compatibility is weak',
      percent: factorPercent('temporal'),
      source: 'ranking[].factors.temporal',
      detail: compatibility.insideRegionRelation ? `Region relation: ${compatibility.insideRegionRelation}` : null,
    }),
    dimension({
      key: 'trajectory',
      label: 'Trajectory plausibility',
      supportLabel: 'Track alignment',
      cautionLabel: 'Weak track alignment',
      percent: factorPercent('trajectory'),
      source: 'ranking[].factors.trajectory',
      detail: numberOrNull(compatibility.plausibleSegmentFraction) != null
        ? `${pct(compatibility.plausibleSegmentFraction)}% of in-window segments physically plausible`
        : null,
    }),
    dimension({
      key: 'behaviour',
      label: 'Behaviour evidence',
      supportLabel: 'Behavioural corroboration',
      cautionLabel: 'Behavioural evidence is weak',
      percent: factorPercent('behaviour'),
      source: 'ranking[].factors.behaviour',
      detail: entry?.behaviour?.description ?? null,
      note: entry?.behaviour?.isAnomaly === true && entry?.behaviour?.scoredEligible === false
        ? 'Behavioural anomaly reported as context only: the vessel was not in the region during the window.'
        : null,
    }),
    dimension({
      key: 'aisCoverage',
      label: 'AIS coverage',
      supportLabel: 'AIS coverage over the window',
      cautionLabel: 'AIS coverage gap',
      percent: aisCoveragePercent(compatibility, releaseWindow),
      source: 'ranking[].compatibility.windowCoverageSeconds / origin.releaseWindow.durationHours',
      detail: numberOrNull(compatibility.windowCoverageSeconds) != null
        ? `${round(compatibility.windowCoverageSeconds / 3600, 1)} h of reports across a ${round(releaseWindow.durationHours, 1)} h window`
        : null,
    }),
    // A gap carries weight in the engine's own aggregation, but the engine is
    // explicit that the ABSENCE of a gap is not evidence about a vessel. When no
    // gap exists this dimension is therefore reported as CONTEXT: it is displayed
    // and it contributes to the composite, but it is never listed as either
    // supporting or contradicting evidence.
    dimension({
      key: 'gap',
      label: 'AIS gap evidence',
      supportLabel: 'Physically feasible AIS gap',
      cautionLabel: 'AIS gap is not physically feasible',
      percent: factorPercent('gap'),
      source: 'ranking[].factors.gap',
      role: gapAnalysis.hasGap === true ? 'evidence' : 'context',
      detail: gapAnalysis.hasGap === true
        ? `${gapAnalysis.gapCount} gap(s) recorded; feasible: ${gapAnalysis.anyFeasible === true ? 'yes' : 'no'}`
        : 'No AIS gap recorded. The absence of a gap is not evidence either.',
    }),
  ]
}

/* ------------------------------------------------------- the gate itself */

const BAND_EXPLANATION = Object.freeze({
  [SUFFICIENCY.HIGH]:
    'Observation quality and this candidate’s recorded movement are mutually compatible across every dimension the engine scored. Continue to corroborate before relying on this assessment.',
  [SUFFICIENCY.MODERATE]:
    'Additional corroborating evidence is recommended.',
  [SUFFICIENCY.INSUFFICIENT]:
    'The available evidence does not currently support prioritising one candidate. Treat the ordering as an agenda for review, not as a finding.',
})

/**
 * Deterministic evidence sufficiency assessment for one candidate.
 *
 * The composite is a weighted mean over the dimensions the API actually
 * supplied, re-normalised by the weight that was available. It is a summary of
 * compatibility between existing evidence items - it is never rendered as, or
 * convertible into, a probability of responsibility.
 */
export function assessEvidenceSufficiency({ investigation, detection, candidate } = {}) {
  const T = SUFFICIENCY_THRESHOLDS
  const dimensions = sufficiencyDimensions({ investigation, detection, candidate })
  const scored = dimensions.filter((d) => d.available && numberOrNull(d.weight) != null)
  const weightSum = scored.reduce((sum, d) => sum + d.weight, 0)
  const weighted = scored.reduce((sum, d) => sum + d.percent * d.weight, 0)
  const composite = weightSum > 0 ? round(weighted / weightSum, 1) : null

  const missingCritical = dimensions.filter((d) => d.critical && !d.available)
  const contradictions = contradictingFactors(candidate)

  let status
  if (composite == null || missingCritical.length > 0) {
    status = SUFFICIENCY.INSUFFICIENT
  } else if (composite >= T.high && contradictions.length <= T.maxContradictionsForHigh) {
    status = SUFFICIENCY.HIGH
  } else if (composite >= T.moderate) {
    status = SUFFICIENCY.MODERATE
  } else {
    status = SUFFICIENCY.INSUFFICIENT
  }

  // A dimension-specific caution floor: origin and AIS coverage are called out
  // explicitly when they sit below the floors declared in the tuning block, even
  // though they clear the generic supporting threshold.
  const cautionFloor = { origin: T.originCautionBelow, aisCoverage: T.aisCoverageCautionBelow }

  // A dimension is "supporting" only when it is available, not context-only, at
  // or above the supporting threshold, and carrying no explicit caution. A
  // dimension is never reported as both supporting and a caution.
  const flagged = new Set()
  const caution = []
  for (const d of dimensions) {
    if (!d.available) {
      flagged.add(d.key)
      caution.push(point(`${d.label} not available`, d.source, d.unavailableReason))
      continue
    }
    const floor = cautionFloor[d.key]
    const belowFloor = numberOrNull(floor) != null && d.percent < floor
    if (d.role !== 'context' && (d.percent < T.supportingDimensionPercent || belowFloor)) {
      flagged.add(d.key)
      caution.push(point(d.cautionLabel, d.source, d.detail))
    }
  }

  const supporting = dimensions
    .filter((d) => d.available && d.role !== 'context' && !flagged.has(d.key) && d.percent >= T.supportingDimensionPercent)
    .map((d) => point(d.supportLabel, d.source, d.detail))

  // The binding constraint: the weakest available dimension that is not
  // context-only. Naming it tells the investigator which input to improve first.
  const ranked = dimensions
    .filter((d) => d.available && d.role !== 'context')
    .sort((a, b) => a.percent - b.percent)
  const limiting = ranked[0] || null

  return {
    available: true,
    status,
    tone: SUFFICIENCY_TONE[status],
    composite,
    compositeDisplay: composite == null ? 'Not available' : `${composite}%`,
    dimensions,
    supporting,
    caution,
    contradictions,
    missingCritical: missingCritical.map((d) => point(`${d.label} is required for this assessment`, d.source, d.unavailableReason)),
    limiting: limiting
      ? point(limiting.label, limiting.source, `${limiting.percent}% of its own maximum`)
      : null,
    explanation: BAND_EXPLANATION[status],
    standing: ASSESSMENT_STANDING,
    // Named explicitly so the UI and the tests agree on what this is not.
    isProbability: false,
  }
}
/* ============================================================ FEATURE 2
 * Uncertainty propagation: observation -> origin -> window -> correlation ->
 * investigation confidence. Each layer states its own confidence if the API
 * published one, and says "Not available" if it did not. No radius, accuracy or
 * error value is ever synthesised; the one radius shown is the model's own
 * reported internal spread (`origin.region.spreadKm`).
 * ====================================================================== */

export const UNCERTAINTY_LAYERS = Object.freeze([
  { id: 'observation', label: 'Observation', caption: 'the SAR scene and its dark formation' },
  { id: 'origin', label: 'Probable origin region', caption: 'reconstructed backwards from the slick' },
  { id: 'window', label: 'Release window', caption: 'candidate window supplied with the case' },
  { id: 'correlation', label: 'Vessel correlation', caption: 'this candidate’s recorded movement' },
  { id: 'confidence', label: 'Investigation confidence', caption: 'evidence sufficiency composite' },
])

/** Neutral wording reused across panels, so the vocabulary cannot drift. */
const UNCERTAINTY_LANGUAGE = Object.freeze({
  origin: 'the probable origin region is not yet tightly constrained',
  window: 'the release window carries no published confidence at all',
  composite: 'the composite evidence sufficiency sits below the confident band',
})

/** How each uncertainty layer relates to reality, reusing the timeline vocabulary. */
const LAYER_STATUS = Object.freeze({
  observation: EVIDENCE_STATUS.OBSERVED,
  origin: EVIDENCE_STATUS.MODELLED,
  window: EVIDENCE_STATUS.PRIOR,
  correlation: EVIDENCE_STATUS.ANALYTICAL,
  confidence: EVIDENCE_STATUS.ANALYTICAL,
})

function layer({ id, label, caption, percent, source, detail = null, note = null, radiusKm }) {
  return {
    id,
    label,
    caption,
    status: LAYER_STATUS[id] ?? EVIDENCE_STATUS.ANALYTICAL,
    percent,
    available: percent != null,
    display: percent == null ? 'Not available' : `${percent}%`,
    source,
    detail,
    note,
    // Only ever the API's own reported spread. `null` means the API published no
    // radius, and the UI must say so rather than estimate one.
    radiusKm: radiusKm === undefined ? null : numberOrNull(radiusKm),
  }
}

/**
 * The uncertainty cascade for one candidate.
 *
 * `layers` is in causal order, so the console can render the chain the method
 * actually follows. `uncertaintyNote` is built only from layers that genuinely
 * carry uncertainty - a layer the API published a solid value for is not
 * described as uncertain.
 */
export function uncertaintyChain({ investigation, detection, candidate, sufficiency } = {}) {
  const region = investigation?.origin?.region || {}
  const releaseWindow = investigation?.origin?.releaseWindow || {}
  const compatibility = candidate?.compatibility || {}
  const assessment = sufficiency || assessEvidenceSufficiency({ investigation, detection, candidate })

  const layers = [
    layer({
      id: 'observation',
      label: 'Observation',
      caption: UNCERTAINTY_LAYERS[0].caption,
      percent: pct(detection?.detectionConfidence),
      source: 'detection.detectionConfidence',
      detail: [detection?.classification, detection?.sensor?.name].filter(Boolean).join(' · ') || null,
      note: detection?.detectionConfidenceNote ?? null,
    }),
    layer({
      id: 'origin',
      label: UNCERTAINTY_LAYERS[1].label,
      caption: UNCERTAINTY_LAYERS[1].caption,
      percent: pct(region.confidence),
      source: 'origin.region.confidence',
      detail: numberOrNull(region.areaKm2) != null ? `${round(region.areaKm2, 1)} km² probable origin region` : null,
      note: 'Reported as a region, never as a single point. Confidence reflects internal model spread, not scientific accuracy.',
      radiusKm: region.spreadKm,
    }),
    layer({
      id: 'window',
      label: UNCERTAINTY_LAYERS[2].label,
      caption: UNCERTAINTY_LAYERS[2].caption,
      percent: null,
      source: 'origin.releaseWindow',
      detail: releaseWindow.start && releaseWindow.end
        ? `${releaseWindow.start} → ${releaseWindow.end} (${round(releaseWindow.durationHours, 1)} h)`
        : null,
      note: 'The response carries no confidence value for the release window, so none is shown. It is a case-input prior, not a quantity this system estimated from the slick.',
    }),
    layer({
      id: 'correlation',
      label: UNCERTAINTY_LAYERS[3].label,
      caption: UNCERTAINTY_LAYERS[3].caption,
      percent: pct(compatibility.plausibleSegmentFraction),
      source: 'ranking[].compatibility.plausibleSegmentFraction',
      detail: numberOrNull(compatibility.recordsInWindow) != null
        ? `${compatibility.recordsInWindow} AIS records inside the window`
        : null,
      note: 'A physical-plausibility measure of the recorded track, not a probability that this vessel was the source of the slick.',
    }),
    layer({
      id: 'confidence',
      label: UNCERTAINTY_LAYERS[4].label,
      caption: UNCERTAINTY_LAYERS[4].caption,
      percent: assessment.composite,
      source: 'forensics.sufficiency (derived from detection.detectionConfidence, origin.region.confidence, ranking[].factors)',
      detail: assessment.composite == null
        ? null
        : `Weighted mean over ${assessment.dimensions.filter((d) => d.available).length} of ${assessment.dimensions.length} available dimensions`,
      note: assessment.standing,
    }),
  ]

  const uncertain = []
  if ((layers[1].percent ?? 100) < 90) uncertain.push(UNCERTAINTY_LANGUAGE.origin)
  if (!layers[2].available) uncertain.push(UNCERTAINTY_LANGUAGE.window)
  if (layers[4].percent != null && layers[4].percent < SUFFICIENCY_THRESHOLDS.high) {
    uncertain.push(UNCERTAINTY_LANGUAGE.composite)
  }

  const radiusKm = layers[1].radiusKm

  return {
    layers,
    uncertain,
    uncertaintyNote: uncertain.length > 0
      ? `Uncertainty remains: ${uncertain.join('; ')}.`
      : 'Every layer published a quality value, but uncertainty is never zero in a reconstruction of this kind.',
    // The API's own radius, surfaced verbatim when present; otherwise the UI is
    // handed an explicit "Not available" rather than a number to print.
    radiusKm,
    radiusDisplay: radiusKm == null ? 'Not available' : `± ${round(radiusKm, 3)} km internal model spread`,
    radiusSource: 'origin.region.spreadKm',
  }
}
/* ============================================================ FEATURE 3
 * Competing hypotheses. ABYSS is required to show that it does not force one
 * answer, so every hypothesis the data can evaluate is listed with the evidence
 * for and against it. A hypothesis the available data cannot evaluate is listed
 * with an explicit zero-evidence status rather than being quietly dropped or
 * padded with invented support.
 * ====================================================================== */

export const HYPOTHESIS_IDS = Object.freeze({
  CANDIDATE: 'candidate-vessel',
  LOOK_ALIKE: 'natural-biogenic',
  INFRASTRUCTURE: 'infrastructure-or-platform',
  UNRESOLVED: 'unknown-insufficient-evidence',
})

/** Sufficiency band -> hypothesis status for the candidate-vessel hypothesis. */
const CANDIDATE_STATUS = Object.freeze({
  [SUFFICIENCY.HIGH]: HYPOTHESIS_STATUS.SUPPORTED,
  [SUFFICIENCY.MODERATE]: HYPOTHESIS_STATUS.PARTIAL,
  [SUFFICIENCY.INSUFFICIENT]: HYPOTHESIS_STATUS.WEAK,
})

function hypothesis({
  id,
  title,
  statement,
  status,
  supporting = [],
  contradicting = [],
  uncertainty = [],
  explanation,
  sources = [],
  assessable = true,
}) {
  return {
    id,
    title,
    statement,
    status,
    tone: HYPOTHESIS_TONE[status],
    supporting,
    contradicting,
    uncertainty,
    explanation,
    sources,
    assessable,
    // Deliberately explicit: no numeric probability is attached to any
    // hypothesis, because the underlying system publishes no calibrated one.
    probability: null,
  }
}

/* ------------------------------------------------- the candidate vessel */

function candidateHypothesis(candidate, assessment, chain) {
  const name = candidate?.name || (candidate?.mmsi ? `MMSI ${candidate.mmsi}` : 'The highest-priority candidate')
  const compatibility = candidate?.compatibility || {}
  const inside = compatibility.insideRegionDuringWindow === true

  return hypothesis({
    id: HYPOTHESIS_IDS.CANDIDATE,
    title: 'Candidate vessel hypothesis',
    statement: inside
      ? `${name} was recorded inside the probable origin region while the release window was open, and its recorded movement is physically consistent with a position there.`
      : `${name} holds the highest aggregated evidence compatibility, but its record does not place it inside the probable origin region during the release window.`,
    status: CANDIDATE_STATUS[assessment.status] ?? HYPOTHESIS_STATUS.NO_DATA,
    supporting: assessment.supporting,
    contradicting: assessment.contradictions,
    uncertainty: chain.uncertain.length > 0 ? [chain.uncertaintyNote] : [],
    explanation:
      `Evidence sufficiency is ${assessment.status} at a composite of ${assessment.compositeDisplay} across the dimensions the API supplied. ` +
      'That composite summarises how far existing evidence items are mutually compatible. It is not a probability that this vessel caused the slick.',
    sources: ['ranking[].compatibility', 'ranking[].factors', 'ranking[].behaviour', 'ranking[].gapAnalysis'],
  })
}

/* ------------------------------------------- natural / biogenic look-alike */

/**
 * Built strictly from `detection.lookAlikeAssessment`, including the classes the
 * API declares it did NOT assess. Those un-assessed classes are the hypothesis's
 * actual supporting evidence: they are the reason it cannot be dismissed.
 */
function lookAlikeHypothesis(detection) {
  const la = detection?.lookAlikeAssessment || null
  const sources = ['detection.lookAlikeAssessment']

  if (!la) {
    return hypothesis({
      id: HYPOTHESIS_IDS.LOOK_ALIKE,
      title: 'Natural / biogenic look-alike hypothesis',
      statement: 'The dark formation may be a natural or biogenic film, a radar artefact or a sea-state variation rather than oil.',
      status: HYPOTHESIS_STATUS.NO_DATA,
      explanation: 'The response carries no look-alike assessment, so this hypothesis can be neither supported nor dismissed from the available data.',
      sources,
      assessable: false,
    })
  }

  const notAssessed = Array.isArray(la.notAssessedClasses) ? la.notAssessedClasses : []
  const checked = Array.isArray(la.checkedClasses) ? la.checkedClasses : []

  const supporting = notAssessed.map((cls) =>
    point(`${cls} — reported as not assessed for this scene`, 'detection.lookAlikeAssessment.notAssessedClasses'),
  )

  const contradicting = []
  if (la.lowWindArea === false) {
    contradicting.push(
      point(
        `Low-wind calm area excluded: ${round(la.windSpeedMs, 1)} m/s at the slick centroid against a ${round(la.thresholdMs, 1)} m/s threshold`,
        'detection.lookAlikeAssessment.lowWindArea',
      ),
    )
  }

  let status
  if (la.lookAlikeWarning === true) {
    // The engine itself flagged a possible look-alike: this hypothesis leads.
    status = HYPOTHESIS_STATUS.SUPPORTED
  } else if (notAssessed.length > 0) {
    status = HYPOTHESIS_STATUS.PARTIAL
  } else if (checked.length > 0) {
    status = HYPOTHESIS_STATUS.WEAK
  } else {
    status = HYPOTHESIS_STATUS.NO_DATA
  }

  return hypothesis({
    id: HYPOTHESIS_IDS.LOOK_ALIKE,
    title: 'Natural / biogenic look-alike hypothesis',
    statement: 'The dark formation may be a natural or biogenic surface film, a radar artefact or a sea-state variation rather than an oil slick.',
    status,
    supporting,
    contradicting,
    uncertainty: notAssessed.length > 0
      ? [`${notAssessed.length} of ${(la.classesConsidered || []).length} look-alike classes were not assessed, so this hypothesis cannot be closed from a single scene.`]
      : [],
    explanation: Array.isArray(la.notes) ? la.notes.join(' ') : 'No explanatory note accompanies the look-alike assessment.',
    sources,
  })
}
/* -------------------------------------------- infrastructure / platform */

/**
 * Listed because the question is a standard one in an oil-spill investigation,
 * but reported with ZERO supporting evidence: no infrastructure, pipeline or
 * terminal source is integrated, and nothing is invented to stand in for one.
 */
function infrastructureHypothesis() {
  return hypothesis({
    id: HYPOTHESIS_IDS.INFRASTRUCTURE,
    title: 'Offshore infrastructure / platform hypothesis',
    statement: 'A fixed installation, pipeline, terminal or port operation inside the probable origin region could account for the release.',
    status: HYPOTHESIS_STATUS.NO_DATA,
    uncertainty: ['No infrastructure, pipeline or terminal dataset is integrated, so this hypothesis cannot be evaluated from the current response.'],
    explanation:
      'ABYSS reports this hypothesis as evaluable in principle but not assessed: no infrastructure source is integrated, and no supporting evidence is invented to stand in for one. Integrating such a source is a data task, not a modelling one.',
    sources: [],
    assessable: false,
  })
}

/* --------------------------------------- unknown / insufficient evidence */

function unresolvedHypothesis(investigation, assessment) {
  const tieGroups = Array.isArray(investigation?.ranking?.tieGroups) ? investigation.ranking.tieGroups : []
  const stats = investigation?.statistics || {}
  const largest = tieGroups.reduce(
    (best, group) => (Array.isArray(group) && group.length > (best ? best.length : 0) ? group : best),
    null,
  )

  const supporting = []
  if (largest && largest.length > 1) {
    supporting.push(
      point(
        `${largest.length} candidates share an identical score, so the available evidence does not separate them`,
        'investigation.ranking.tieGroups',
      ),
    )
  }
  if (numberOrNull(stats.tieGroupCount) != null && stats.tieGroupCount > 0) {
    supporting.push(point(`${stats.tieGroupCount} tie group(s) reported across the ranking`, 'investigation.statistics.tieGroupCount'))
  }
  if (assessment.missingCritical.length > 0) {
    supporting.push(point('A required dimension of the assessment is missing from the response', assessment.missingCritical[0].source))
  }

  let status
  if (assessment.status === SUFFICIENCY.INSUFFICIENT) status = HYPOTHESIS_STATUS.SUPPORTED
  else if (supporting.length > 0) status = HYPOTHESIS_STATUS.PARTIAL
  else status = HYPOTHESIS_STATUS.WEAK

  const vessels = numberOrNull(stats.vesselsScored)

  return hypothesis({
    id: HYPOTHESIS_IDS.UNRESOLVED,
    title: 'Unknown / insufficient-evidence hypothesis',
    statement: 'The release came from a source that is not represented, or not adequately covered, by the evidence currently held.',
    status,
    supporting,
    contradicting: [],
    uncertainty: assessment.limiting
      ? [`The binding constraint on this assessment is ${assessment.limiting.label} at ${assessment.limiting.detail}.`]
      : [],
    explanation:
      `Scored against ${vessels == null ? 'the ranked' : vessels} candidates. ` +
      'Where candidates share an identical score the ordering is a deterministic display choice, not an evidential distinction, so the possibility that the source lies outside the correlated set stays open.',
    sources: ['investigation.ranking.tieGroups', 'investigation.statistics'],
  })
}

/**
 * All hypotheses the case can speak to, each with its evidence for and against.
 *
 * Order is deliberate: the leading hypothesis from the available data first, then
 * the alternatives that could displace it, then the state of the unresolved
 * question itself.
 */
export function competingHypotheses({ investigation, detection, candidate, sufficiency, uncertainty } = {}) {
  const assessment = sufficiency || assessEvidenceSufficiency({ investigation, detection, candidate })
  const chain = uncertainty || uncertaintyChain({ investigation, detection, candidate, sufficiency: assessment })

  return {
    hypotheses: [
      candidateHypothesis(candidate, assessment, chain),
      lookAlikeHypothesis(detection),
      infrastructureHypothesis(),
      unresolvedHypothesis(investigation, assessment),
    ],
    statuses: HYPOTHESIS_STATUS,
    note: 'Each hypothesis is listed with the evidence for and against it. No numeric probability is attached to any hypothesis, because the underlying system publishes no calibrated probability.',
  }
}
/* ============================================================ FEATURE 4
 * Candidate comparison. Answers "why does A rank differently from B" by
 * comparing the same engine factors side by side, and by naming which axes each
 * candidate leads. Leads are phrased as compatibility and investigation
 * priority; neither candidate is described as responsible for the slick.
 * ====================================================================== */

/** Ordinal position of each sufficiency band - an ordering, not a probability. */
export const SUFFICIENCY_RANK = Object.freeze({
  [SUFFICIENCY.HIGH]: 2,
  [SUFFICIENCY.MODERATE]: 1,
  [SUFFICIENCY.INSUFFICIENT]: 0,
})

/**
 * One comparable axis. `lowerIsBetter` inverts the winner so that "fewer
 * contradicting factors" and "less uncertainty" count as leads, which is how an
 * investigator reads them.
 */
function comparisonAxis({
  key,
  label,
  source,
  aRaw,
  bRaw,
  aDisplay,
  bDisplay,
  max = null,
  lowerIsBetter = false,
  advantagePhrase,
  disadvantagePhrase,
  note = null,
}) {
  const a = numberOrNull(aRaw)
  const b = numberOrNull(bRaw)

  let winner = null
  if (a != null && b != null && a !== b) {
    const aLeads = lowerIsBetter ? a < b : a > b
    winner = aLeads ? 'a' : 'b'
  }

  const asSide = (raw, display) => ({
    value: raw,
    display: display ?? (raw == null ? 'Not available' : String(raw)),
    percent: raw == null || !(max > 0) ? null : clamp01(raw / max),
  })

  return {
    key,
    label,
    source,
    a: asSide(a, aDisplay),
    b: asSide(b, bDisplay),
    delta: a == null || b == null ? null : Number((a - b).toFixed(3)),
    winner,
    lowerIsBetter,
    advantagePhrase,
    disadvantagePhrase,
    note,
  }
}
/** The engine's five factors, compared as lead/don't-lead axes. */
const FACTOR_AXES = Object.freeze([
  { key: 'spatial', label: 'Spatial score', advantagePhrase: 'stronger spatial compatibility', disadvantagePhrase: 'weaker spatial compatibility' },
  { key: 'temporal', label: 'Temporal score', advantagePhrase: 'stronger temporal compatibility', disadvantagePhrase: 'weaker temporal compatibility' },
  { key: 'trajectory', label: 'Trajectory score', advantagePhrase: 'stronger trajectory alignment', disadvantagePhrase: 'weaker trajectory alignment' },
  { key: 'behaviour', label: 'Behaviour score', advantagePhrase: 'stronger behavioural corroboration', disadvantagePhrase: 'weaker behavioural corroboration' },
  { key: 'gap', label: 'AIS gap / context score', advantagePhrase: 'stronger AIS gap evidence', disadvantagePhrase: 'weaker AIS gap evidence' },
])

/** Everything the comparison needs about one side, computed once. */
function comparisonSide(entry, investigation, detection) {
  const assessment = assessEvidenceSufficiency({ investigation, detection, candidate: entry })
  return {
    entry,
    assessment,
    chain: uncertaintyChain({ investigation, detection, candidate: entry, sufficiency: assessment }),
    factors: Object.fromEntries(factorRows(entry.factors).map((f) => [f.key, f])),
    mmsi: entry.mmsi,
    name: entry.name || `MMSI ${entry.mmsi}`,
    rank: entry.rank ?? null,
    totalScore: numberOrNull(entry.totalScore),
    status: assessment.status,
    composite: assessment.composite,
  }
}

/**
 * Side-by-side comparison of two candidates.
 *
 * Returns an explicit `available: false` when either MMSI is not in the ranking,
 * so the UI can say why it cannot compare rather than rendering empty bars.
 */
export function compareCandidates({ investigation, detection, mmsiA, mmsiB } = {}) {
  const entries = rankingEntries(investigation)
  const entryA = entries.find((e) => String(e.mmsi) === String(mmsiA)) || null
  const entryB = entries.find((e) => String(e.mmsi) === String(mmsiB)) || null

  if (!entryA || !entryB) {
    const missing = !entryA && !entryB ? 'both candidates' : !entryA ? 'candidate A' : 'candidate B'
    return {
      available: false,
      reason: `No ranked candidate matches ${missing} in this API response.`,
      a: null,
      b: null,
      axes: [],
      aAdvantages: [],
      bAdvantages: [],
      summary: null,
      note: null,
    }
  }

  const a = comparisonSide(entryA, investigation, detection)
  const b = comparisonSide(entryB, investigation, detection)
  const releaseWindow = investigation?.origin?.releaseWindow || {}

  const factorAxis = (def) => {
    const fa = a.factors[def.key] || {}
    const fb = b.factors[def.key] || {}
    return comparisonAxis({
      key: def.key,
      label: def.label,
      source: `ranking[].factors.${def.key}`,
      aRaw: fa.available ? fa.points : null,
      bRaw: fb.available ? fb.points : null,
      aDisplay: fa.available ? `${round(fa.points, 1)} / ${fa.maxPoints}` : null,
      bDisplay: fb.available ? `${round(fb.points, 1)} / ${fb.maxPoints}` : null,
      advantagePhrase: def.advantagePhrase,
      disadvantagePhrase: def.disadvantagePhrase,
      note: fa.maxPoints !== fb.maxPoints ? 'Scored against different maximums.' : null,
    })
  }

  const coverageA = aisCoveragePercent(entryA.compatibility, releaseWindow)
  const coverageB = aisCoveragePercent(entryB.compatibility, releaseWindow)

  const axes = [
    comparisonAxis({
      key: 'totalScore',
      label: 'Overall investigation score',
      source: 'ranking[].totalScore',
      aRaw: a.totalScore,
      bRaw: b.totalScore,
      max: 100,
      advantagePhrase: 'higher overall investigation score',
      disadvantagePhrase: 'lower overall investigation score',
    }),
    ...FACTOR_AXES.map(factorAxis),
    comparisonAxis({
      key: 'aisCoverage',
      label: 'AIS coverage over the window',
      source: 'ranking[].compatibility.windowCoverageSeconds / origin.releaseWindow.durationHours',
      aRaw: coverageA,
      bRaw: coverageB,
      aDisplay: coverageA == null ? null : `${coverageA}%`,
      bDisplay: coverageB == null ? null : `${coverageB}%`,
      max: 100,
      advantagePhrase: 'better AIS coverage over the window',
      disadvantagePhrase: 'larger AIS coverage gap',
    }),
    comparisonAxis({
      key: 'supporting',
      label: 'Supporting evidence items',
      source: 'forensics.sufficiency.supporting',
      aRaw: a.assessment.supporting.length,
      bRaw: b.assessment.supporting.length,
      aDisplay: `${a.assessment.supporting.length}`,
      bDisplay: `${b.assessment.supporting.length}`,
      advantagePhrase: 'more supporting evidence items',
      disadvantagePhrase: 'fewer supporting evidence items',
    }),
    comparisonAxis({
      key: 'contradicting',
      label: 'Contradicting factors',
      source: 'forensics.contradictions (ranking[].compatibility.filters, ranking[].behaviour, ranking[].gapAnalysis)',
      aRaw: a.assessment.contradictions.length,
      bRaw: b.assessment.contradictions.length,
      aDisplay: `${a.assessment.contradictions.length}`,
      bDisplay: `${b.assessment.contradictions.length}`,
      lowerIsBetter: true,
      advantagePhrase: 'fewer contradicting factors',
      disadvantagePhrase: 'more contradicting factors',
    }),
    comparisonAxis({
      key: 'uncertainty',
      label: 'Uncertainty carried',
      source: 'forensics.uncertainty.layers',
      aRaw: a.chain.uncertain.length,
      bRaw: b.chain.uncertain.length,
      aDisplay: `${a.chain.uncertain.length} layer(s)`,
      bDisplay: `${b.chain.uncertain.length} layer(s)`,
      lowerIsBetter: true,
      advantagePhrase: 'less uncertainty carried',
      disadvantagePhrase: 'larger uncertainty',
    }),
    comparisonAxis({
      key: 'sufficiency',
      label: 'Evidence sufficiency',
      source: 'forensics.sufficiency',
      aRaw: SUFFICIENCY_RANK[a.status],
      bRaw: SUFFICIENCY_RANK[b.status],
      aDisplay: a.status,
      bDisplay: b.status,
      max: 2,
      advantagePhrase: 'higher evidence sufficiency band',
      disadvantagePhrase: 'lower evidence sufficiency band',
    }),
  ]
  const aAdvantages = []
  const bAdvantages = []
  for (const axis of axes) {
    if (axis.winner === 'a') {
      aAdvantages.push({ axis: axis.key, label: axis.label, text: axis.advantagePhrase, tone: 'ok' })
      bAdvantages.push({ axis: axis.key, label: axis.label, text: axis.disadvantagePhrase, tone: 'muted' })
    } else if (axis.winner === 'b') {
      bAdvantages.push({ axis: axis.key, label: axis.label, text: axis.advantagePhrase, tone: 'ok' })
      aAdvantages.push({ axis: axis.key, label: axis.label, text: axis.disadvantagePhrase, tone: 'muted' })
    }
  }

  const decidable = axes.filter((axis) => axis.winner != null).length
  const leadsA = axes.filter((axis) => axis.winner === 'a').length
  const leadsB = axes.filter((axis) => axis.winner === 'b').length
  const rankGap = a.rank != null && b.rank != null ? a.rank - b.rank : null

  const rankClause = rankGap == null
    ? `${a.name} and ${b.name} are compared below.`
    : rankGap === 0
      ? `${a.name} and ${b.name} occupy the same rank.`
      : `${a.name} ranks ${a.rank} and ${b.name} ranks ${b.rank}.`

  return {
    available: true,
    a: { mmsi: a.mmsi, name: a.name, rank: a.rank, totalScore: a.totalScore, status: a.status, composite: a.composite },
    b: { mmsi: b.mmsi, name: b.name, rank: b.rank, totalScore: b.totalScore, status: b.status, composite: b.composite },
    axes,
    aAdvantages,
    bAdvantages,
    leadsOn: { a: leadsA, b: leadsB, decidable },
    rankGap,
    summary:
      `${rankClause} Across ${decidable} decidable axes ${a.name} leads on ${leadsA} and ${b.name} on ${leadsB}` +
      (aAdvantages.length > 0 ? `; ${a.name}'s widest single lead is ${aAdvantages[0].text}.` : '.'),
    note: 'This comparison orders investigation priority by how far existing evidence is mutually compatible. A higher score means higher compatibility with the observed event, not responsibility for it.',
  }
}
/* ============================================================ FEATURE 5
 * Hypothesis replay. Replays the reconstruction ABYSS already holds -
 * the observed slick, the probable origin region and the modelled backward
 * drift path - against the candidate's recorded track, and reports the engine's
 * own compatibility flags.
 *
 * No ocean physics is run here and no overlap percentage is computed: the
 * analytic question answered is "could this candidate's recorded movement be
 * consistent with the observed event?", never "did it cause it".
 * ====================================================================== */

export const REPLAY_STAGES = Object.freeze([
  { id: 'track', label: 'Candidate trajectory', caption: 'recorded AIS movement for this vessel' },
  { id: 'origin', label: 'Probable origin region', caption: 'reconstructed backwards from the slick' },
  { id: 'drift', label: 'Modelled backward drift', caption: 'the model path linking slick to origin' },
  { id: 'slick', label: 'Observed slick', caption: 'the SAR-observed dark formation' },
  { id: 'forward', label: 'Forward model replay', caption: 'projects drift forward from the origin' },
])

/**
 * A GeoJSON geometry -> [{lat, lon}] via the tested geo helper.
 *
 * A Polygon's `coordinates` is an array of rings, a LineString's is the point
 * list itself, so the outer ring is selected by type first and then by shape.
 * Without this the ring arrays themselves would be silently filtered out and the
 * replay would render nothing.
 */
const geoPoints = (geometry) => {
  const coordinates = geometry?.coordinates
  if (!Array.isArray(coordinates)) return []
  if (geometry?.type === 'Polygon') return ringToLatLon(coordinates[0])
  if (Array.isArray(coordinates[0]) && Array.isArray(coordinates[0][0])) {
    return ringToLatLon(coordinates[0])
  }
  return ringToLatLon(coordinates)
}

/**
 * Forward-drift geometry, read from the shape the real drift endpoint actually
 * returns: `trajectories[].path` particle tracks and an `uncertainty_polygon`
 * ring, both as `[{lat, lon}]` / `[[lat, lon], ...]`.
 *
 * A GeoJSON `geometry` is also accepted so a future provider can publish the
 * forward footprint in the same form as the origin region.
 */
function forecastGeometry(forecast) {
  if (!forecast) return { paths: [], polygon: [], source: null }
  const paths = (Array.isArray(forecast.trajectories) ? forecast.trajectories : [])
    .map((t) => normalisePoints(Array.isArray(t?.path) ? t.path : t))
    .filter((points) => points.length >= 2)
  if (paths.length > 0) return { paths, polygon: [], source: 'forecast.trajectories[].path' }

  const polygon = normalisePoints(forecast.uncertainty_polygon)
  if (polygon.length >= 3) return { paths: [], polygon, source: 'forecast.uncertainty_polygon' }

  const geometry = geoPoints(forecast.geometry || forecast.polygon || null)
  if (geometry.length >= 3) return { paths: [], polygon: geometry, source: 'forecast.geometry' }

  return { paths: [], polygon: [], source: null }
}

const REPLAY_QUESTION = 'Could this candidate’s recorded movement be consistent with the observed event?'

const REPLAY_STANDING =
  'A replay of existing reconstruction and forecast data. Consistency between a track and the observed event does not establish that this vessel caused the slick.'

/** One replay stage: what exists, where it came from, and what it shows. */
function replayStage({ id, available, display, source, detail = null, note = null }) {
  const meta = REPLAY_STAGES.find((s) => s.id === id) || {}
  return {
    id,
    label: meta.label ?? id,
    caption: meta.caption ?? null,
    available,
    display,
    source,
    detail,
    note,
  }
}

/**
 * Build the hypothesis replay for one candidate.
 *
 * @param {object} detection       the /detect payload's `detection`
 * @param {object} investigation   the /investigate payload's `investigation`
 * @param {object|null} candidate  the selected ranking entry
 * @param {object|null} trajectory the reconstructed AIS track bundle for it
 * @param {object|null} forecast   a forward drift output, when one was supplied
 */
export function buildHypothesisReplay({ investigation, detection, candidate, trajectory, forecast } = {}) {
  if (!candidate) {
    return {
      available: false,
      reason: 'No candidate is selected, so there is no trajectory to replay.',
      stages: [],
      geo: null,
      compatibility: null,
      forward: null,
      question: REPLAY_QUESTION,
      answer: null,
      standing: REPLAY_STANDING,
    }
  }

  const region = investigation?.origin?.region || {}
  const drift = investigation?.origin?.drift || {}
  const slickGeometry = detection?.characterisation?.geometry || null
  const slickAreaKm2 = numberOrNull(detection?.characterisation?.areaKm2)
  const trackStats = trajectory?.stats || null
  const recordCount = numberOrNull(trackStats?.recordCount)
  const backdrift = normalisePoints(drift.backdriftPath)

  const forward = forecastGeometry(forecast)
  const forwardPaths = forward.paths
  const forwardPolygon = forward.polygon
  const forwardVerts = forwardPaths.length > 0
    ? forwardPaths.reduce((sum, p) => sum + p.length, 0)
    : forwardPolygon.length
  const forwardAvailable = forwardPaths.length > 0 || forwardPolygon.length >= 3
  const forwardLabel = forwardPaths.length > 0
    ? `${forwardPaths.length} modelled particle track(s)`
    : 'Modelled forward footprint'

  // Geometry kept in geographic coordinates; the component owns the projection so
  // this module stays independent of any drawing surface.
  const geo = {
    slick: geoPoints(slickGeometry),
    origin: geoPoints(region.geometry),
    backdrift,
    track: geoPoints(trajectory?.geometry),
    forwardPaths,
    forwardPolygon,
  }

  const filters = candidate.compatibility?.filters || {}
  const checks = [
    { key: 'spatial', label: 'Spatial containment', pass: filters.spatial === true, source: 'ranking[].compatibility.filters.spatial' },
    { key: 'temporal', label: 'Release-window presence', pass: filters.temporal === true, source: 'ranking[].compatibility.filters.temporal' },
    { key: 'trajectory', label: 'Physical plausibility of the track', pass: filters.trajectory === true, source: 'ranking[].compatibility.filters.trajectory' },
  ]
  const passed = checks.filter((c) => c.pass)
  const failed = checks.filter((c) => !c.pass)

  const stages = [
    replayStage({
      id: 'track',
      available: geo.track.length >= 2,
      display: geo.track.length >= 2
        ? `${recordCount == null ? geo.track.length : recordCount} recorded positions`
        : 'Not loaded for this vessel',
      source: 'trajectory.stats',
      detail: trackStats?.observedDistanceKm != null ? `${round(trackStats.observedDistanceKm, 1)} km observed distance` : null,
      note: geo.track.length >= 2 ? null : 'The trajectory bundle for this vessel is not loaded, so no track is drawn.',
    }),
    replayStage({
      id: 'origin',
      available: geo.origin.length >= 3,
      display: numberOrNull(region.areaKm2) != null ? `${round(region.areaKm2, 1)} km² probable region` : 'Not available',
      source: 'origin.region',
      detail: numberOrNull(region.confidence) != null ? `Reconstruction confidence ${confidencePercent(region.confidence)}%` : null,
      note: geo.origin.length >= 3 ? null : 'The response carries no origin region geometry.',
    }),
    replayStage({
      id: 'drift',
      available: backdrift.length >= 2,
      display: backdrift.length >= 2 ? `${backdrift.length}-point modelled path` : 'Not available',
      source: 'origin.drift.backdriftPath',
      detail: drift.integration ?? null,
      note: drift.parametersArePrototypeValues === true
        ? 'Prototype drift parameters. The model is reported as uncalibrated by the API itself.'
        : null,
    }),
    replayStage({
      id: 'slick',
      available: geo.slick.length >= 3,
      display: slickAreaKm2 != null ? `${round(slickAreaKm2, 1)} km² observed slick` : 'Not available',
      source: 'detection.characterisation.geometry',
      detail: detection?.classification ?? null,
      note: null,
    }),
    replayStage({
      id: 'forward',
      available: forwardAvailable,
      display: forwardAvailable ? forwardLabel : 'Not available for this case',
      // Named only when a forecast payload was actually supplied: an absent
      // forward output has no API path to point at.
      source: forwardAvailable ? forward.source : 'not-integrated: no forward drift output in this response',
      detail: forwardAvailable ? `${forwardVerts} plotted vertices` : null,
      note: forwardAvailable
        ? 'Model replay available from existing forecast data. No overlap percentage is computed because the system publishes no calibrated overlap or error metric.'
        : 'No forward drift output was supplied with this response, so no model replay is drawn and no overlap percentage is computed.',
    }),
  ]
  const answer = failed.length === 0
    ? 'Yes on every dimension the engine checks: the candidate was recorded inside the probable origin region while the release window was open, and its recorded movement is physically plausible. This is consistency with the observed event, not proof that it caused the slick.'
    : `Not on every dimension. ${failed.map((c) => c.label).join(', ')} did not pass, so the recorded movement alone does not account for the observed event.`

  return {
    available: true,
    candidate: { mmsi: candidate.mmsi, name: candidate.name || `MMSI ${candidate.mmsi}` },
    stages,
    geo,
    framedBounds: boundsOf([...geo.slick, ...geo.origin, ...geo.backdrift]),
    frameNote:
      'The plot is fitted to the probable origin region, the observed slick and the modelled path. The candidate track may extend well beyond this frame.',
    compatibility: {
      checks,
      passed,
      failed,
      available: checks.length === 3,
      summary: `${passed.length} of ${checks.length} engine checks pass`,
    },
    forward: {
      available: forwardAvailable,
      // Never true: the API publishes no calibrated overlap or error metric, so
      // the console must not present one.
      overlapAvailable: false,
      message: forwardAvailable
        ? 'Model replay available from existing forecast data'
        : 'Forward model replay unavailable: no forward drift output was supplied',
    },
    question: REPLAY_QUESTION,
    answer,
    standing: REPLAY_STANDING,
  }
}
/* ============================================================ FEATURE 6
 * Reusable investigation status. The console must be able to display an
 * explicit INSUFFICIENT EVIDENCE state, with reasons drawn only from data that
 * actually supports each reason. It is never forced: if the evidence for the
 * selected candidate is adequate, the status says so.
 * ====================================================================== */

export const INVESTIGATION_STATE = Object.freeze({
  ADEQUATE: 'ADEQUATE FOR PRIORITISATION',
  INSUFFICIENT: 'INSUFFICIENT EVIDENCE',
})

export const INVESTIGATION_STATE_TONE = Object.freeze({
  [INVESTIGATION_STATE.ADEQUATE]: 'ok',
  [INVESTIGATION_STATE.INSUFFICIENT]: 'warn',
})

/**
 * Status of the investigation for one candidate.
 *
 * `reasons` are emitted one at a time and each is gated on the field that
 * justifies it, so a reason can never appear without its supporting evidence.
 */
export function investigationStatus({ investigation, detection, candidate, sufficiency } = {}) {
  const assessment = sufficiency || assessEvidenceSufficiency({ investigation, detection, candidate })
  const region = investigation?.origin?.region || {}
  const releaseWindow = investigation?.origin?.releaseWindow || {}
  const la = detection?.lookAlikeAssessment || null
  const stats = investigation?.statistics || {}
  const compatibility = candidate?.compatibility || {}

  const insufficient = assessment.status === SUFFICIENCY.INSUFFICIENT
  const reasons = []

  if (insufficient) {
    for (const gap of assessment.missingCritical) {
      reasons.push(point(`A required input is missing: ${gap.label}`, gap.source, gap.detail))
    }
    if (assessment.composite != null && assessment.composite < SUFFICIENCY_THRESHOLDS.high) {
      reasons.push(
        point(
          `Evidence compatibility is ${assessment.status} at a composite of ${assessment.compositeDisplay}, below the confident band`,
          'forensics.sufficiency',
        ),
      )
    }
    const originPercent = confidencePercent(region.confidence)
    if (originPercent != null && originPercent < SUFFICIENCY_THRESHOLDS.originCautionBelow) {
      reasons.push(point(`Origin uncertainty is high at ${originPercent}% reconstruction confidence`, 'origin.region.confidence'))
    }
    const coverage = aisCoveragePercent(compatibility, releaseWindow)
    if (coverage != null && coverage < 100) {
      reasons.push(point(`AIS coverage is incomplete: ${coverage}% of the release window is covered by records`, 'ranking[].compatibility.windowCoverageSeconds'))
    }
    for (const contradiction of assessment.contradictions) {
      reasons.push(contradiction)
    }
    if (la && Array.isArray(la.notAssessedClasses) && la.notAssessedClasses.length > 0) {
      reasons.push(
        point(
          `Multiple hypotheses remain plausible: ${la.notAssessedClasses.join(', ')} were not assessed`,
          'detection.lookAlikeAssessment.notAssessedClasses',
        ),
      )
    }
    const tieGroups = Array.isArray(investigation?.ranking?.tieGroups) ? investigation.ranking.tieGroups : []
    const inTie = tieGroups.find((group) => Array.isArray(group) && group.some((m) => String(m) === String(candidate?.mmsi)))
    if (inTie && inTie.length > 1) {
      reasons.push(point(`This candidate shares an identical score with ${inTie.length - 1} other candidate(s)`, 'investigation.ranking.tieGroups'))
    }
    if (numberOrNull(stats.vesselsScored) != null && reasons.length > 0) {
      reasons.push(
        point(
          `The assessment covers ${stats.vesselsScored} scored candidates; a source outside that set cannot be excluded`,
          'investigation.statistics.vesselsScored',
        ),
      )
    }
  }

  return {
    state: insufficient ? INVESTIGATION_STATE.INSUFFICIENT : INVESTIGATION_STATE.ADEQUATE,
    tone: INVESTIGATION_STATE_TONE[insufficient ? INVESTIGATION_STATE.INSUFFICIENT : INVESTIGATION_STATE.ADEQUATE],
    insufficient,
    headline: insufficient
      ? 'The available evidence does not currently support prioritising this candidate.'
      : 'The available evidence is adequate to place this candidate in the investigation queue.',
    candidate: candidate
      ? { mmsi: candidate.mmsi, name: candidate.name || `MMSI ${candidate.mmsi}`, rank: candidate.rank ?? null }
      : null,
    sufficiencyStatus: assessment.status,
    composite: assessment.composite,
    compositeDisplay: assessment.compositeDisplay,
    // Reasons are only produced for the insufficient state; an adequate case
    // reports which dimensions carried it instead.
    reasons: insufficient ? reasons : [],
    carrying: insufficient ? [] : assessment.supporting,
    caution: assessment.caution,
    nextEvidence: recommendNextEvidence({ investigation, detection, candidate, sufficiency: assessment }),
    standing: ASSESSMENT_STANDING,
  }
}
/* ============================================================ FEATURE 7
 * Recommended next evidence. Decision support for the investigator, generated
 * only from evidence that is genuinely missing or weak in this response. If
 * nothing is missing, the recommender says so rather than emitting filler.
 * ====================================================================== */

/** Priority ordering for the recommendation list. */
const PRIORITY_ORDER = Object.freeze({ high: 0, medium: 1, low: 2 })

function recommendation({ id, title, why, source, addresses, priority = 'medium' }) {
  return { id, title, why, source, addresses, priority }
}

/**
 * Recommendations for the selected candidate.
 *
 * Every rule is gated on a specific field, so a recommendation appears only when
 * the field that justifies it is present and actually weak.
 */
export function recommendNextEvidence({ investigation, detection, candidate, sufficiency } = {}) {
  const assessment = sufficiency || assessEvidenceSufficiency({ investigation, detection, candidate })
  const region = investigation?.origin?.region || {}
  const releaseWindow = investigation?.origin?.releaseWindow || {}
  const compatibility = candidate?.compatibility || {}
  const la = detection?.lookAlikeAssessment || null
  const out = []

  // Look-alike classes the API itself declares unassessed: the single strongest
  // reason to acquire another observation.
  const notAssessed = la && Array.isArray(la.notAssessedClasses) ? la.notAssessedClasses : []
  if (notAssessed.length > 0) {
    out.push(
      recommendation({
        id: 'optical-confirmation',
        title: 'Acquire optical imagery for confirmation',
        why: `These look-alike classes were not assessed for this scene: ${notAssessed.join(', ')}. Optical imagery can discriminate a natural or biogenic surface film from oil.`,
        source: 'detection.lookAlikeAssessment.notAssessedClasses',
        addresses: 'look-alike hypothesis',
        priority: 'high',
      }),
    )
    out.push(
      recommendation({
        id: 'multi-sensor-relook',
        title: 'Commission a multi-sensor or in-situ re-look of the same area',
        why: 'The look-alike assessment states that a single scene cannot resolve these alternatives and that a real investigation needs multi-sensor or in-situ confirmation.',
        source: 'detection.lookAlikeAssessment.notes',
        addresses: 'look-alike hypothesis',
        priority: 'high',
      }),
    )
  }

  // Origin reconstruction that is not tightly constrained.
  const originPercent = confidencePercent(region.confidence)
  if (originPercent != null && originPercent < 85) {
    out.push(
      recommendation({
        id: 'origin-tightening',
        title: 'Acquire an additional satellite observation to tighten the probable origin region',
        why: `Origin reconstruction confidence is ${originPercent}%${numberOrNull(region.spreadKm) != null ? `, with an internal model spread of ± ${round(region.spreadKm, 3)} km` : ''}. A repeat observation constrains the region directly.`,
        source: 'origin.region.confidence',
        addresses: 'origin uncertainty',
        priority: 'high',
      }),
    )
  }

  // AIS availability over the window.
  const coverage = aisCoveragePercent(compatibility, releaseWindow)
  if (coverage != null && coverage < 100) {
    out.push(
      recommendation({
        id: 'ais-coverage',
        title: 'Verify AIS coverage during the release window',
        why: `Only ${coverage}% of the release window is covered by AIS records for this candidate, so any inference about its presence rests on partial coverage.`,
        source: 'ranking[].compatibility.windowCoverageSeconds',
        addresses: 'AIS coverage gap',
        priority: 'high',
      }),
    )
  }

  // Weak behavioural corroboration for a candidate that is otherwise relevant.
  const behaviourFactor = factorRows(candidate?.factors).find((f) => f.key === 'behaviour')
  if (
    behaviourFactor?.available &&
    compatibility.insideRegionDuringWindow === true &&
    behaviourFactor.percent < 0.5
  ) {
    out.push(
      recommendation({
        id: 'vessel-records',
        title: 'Review vessel log and port records for the release window',
        why: `Behavioural corroboration is weak (${Math.round(behaviourFactor.percent * 100)}% of its own maximum) even though the candidate was inside the region, so documentary evidence is the natural next corroboration.`,
        source: 'ranking[].factors.behaviour',
        addresses: 'behaviour evidence',
        priority: 'medium',
      }),
    )
  }

  // Vessel identity completeness.
  if (candidate && !candidate.imo) {
    out.push(
      recommendation({
        id: 'vessel-identity',
        title: 'Review vessel identity and IMO information',
        why: 'The API returns no IMO for this candidate, so its identity is not independently resolvable from this response alone.',
        source: 'ranking[].mmsi',
        addresses: 'identity completeness',
        priority: 'medium',
      }),
    )
  }

  // Infrastructure source class is absent from the integration. Gated on the
  // payload actually carrying no infrastructure source, so the recommendation
  // disappears by itself once one is integrated.
  const hasInfrastructureSource = Boolean(investigation?.infrastructure || detection?.infrastructure)
  if (!hasInfrastructureSource) {
    out.push(
      recommendation({
        id: 'infrastructure-verification',
        title: 'Verify offshore infrastructure, pipeline or terminal activity inside the probable origin region',
        why: 'No infrastructure dataset is integrated, so the infrastructure hypothesis cannot be assessed either way from this response.',
        source: 'not-integrated: infrastructure dataset',
        addresses: 'infrastructure hypothesis',
        priority: 'medium',
      }),
    )
  }

  // Synthetic data must not be carried into operational use unlabelled.
  if (detection?.synthetic === true) {
    out.push(
      recommendation({
        id: 'real-acquisition',
        title: 'Repeat the assessment on a real acquisition before any operational use',
        why: `This response is flagged synthetic (${detection.datasetLabel || detection.uiLabel || 'demonstration data'}), so its numbers describe a demonstration scene only.`,
        source: 'detection.synthetic',
        addresses: 'data provenance',
        priority: 'medium',
      }),
    )
  }

  // Contradicting factors worth re-examining before the ranking is relied on.
  if (assessment.contradictions.length > 0) {
    out.push(
      recommendation({
        id: 'contradiction-review',
        title: 'Re-examine the contradicting factors before relying on this ranking',
        why: `${assessment.contradictions.length} factor(s) argue against this candidate, led by: ${assessment.contradictions[0].label}.`,
        source: assessment.contradictions[0].source,
        addresses: 'contradicting evidence',
        priority: 'medium',
      }),
    )
  }

  // A tie the available evidence cannot break.
  const tieGroups = Array.isArray(investigation?.ranking?.tieGroups) ? investigation.ranking.tieGroups : []
  const inTie = tieGroups.find((group) => Array.isArray(group) && group.some((m) => String(m) === String(candidate?.mmsi)))
  if (inTie && inTie.length > 1) {
    out.push(
      recommendation({
        id: 'separate-ties',
        title: 'Acquire an observation capable of separating the tied candidates',
        why: `${inTie.length} candidates share an identical score, so the available evidence does not distinguish between them.`,
        source: 'investigation.ranking.tieGroups',
        addresses: 'unresolved hypothesis',
        priority: 'medium',
      }),
    )
  }
  const recommendations = out
    .map((item, index) => ({ ...item, index }))
    .sort((a, b) => (PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority]) || (a.index - b.index))
    .map(({ index, ...item }) => item)

  return {
    recommendations,
    empty: recommendations.length === 0,
    message: recommendations.length === 0
      ? 'No missing or weak evidence was identified in this API response, so no additional evidence is recommended.'
      : 'Decision support only: these are the evidence gaps this response actually shows, not an instruction to act.',
    highPriority: recommendations.filter((r) => r.priority === 'high').length,
  }
}
/* ----------------------------------------------------------- composition */

/**
 * One call that assembles the whole forensic assessment for a candidate, so the
 * panels stay presentational and no two of them recompute the same thing.
 *
 * Every value shared between panels (sufficiency, uncertainty, status) is
 * computed once and passed down, which is also what makes the output comparable
 * between the evidence stage and the review stage.
 */
export function buildForensicAssessment({ investigation, detection, candidate, trajectory, forecast } = {}) {
  const sufficiency = assessEvidenceSufficiency({ investigation, detection, candidate })
  const uncertainty = uncertaintyChain({ investigation, detection, candidate, sufficiency })
  const status = investigationStatus({ investigation, detection, candidate, sufficiency })
  return {
    sufficiency,
    uncertainty,
    status,
    nextEvidence: status.nextEvidence,
    hypotheses: competingHypotheses({ investigation, detection, candidate, sufficiency, uncertainty }),
    replay: buildHypothesisReplay({ investigation, detection, candidate, trajectory, forecast }),
  }
}
