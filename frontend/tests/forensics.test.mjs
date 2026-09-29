import assert from 'node:assert/strict'
import test from 'node:test'
import {
  ASSESSMENT_STANDING,
  HYPOTHESIS_IDS,
  HYPOTHESIS_STATUS,
  INVESTIGATION_STATE,
  SUFFICIENCY,
  SUFFICIENCY_RANK,
  SUFFICIENCY_THRESHOLDS,
  SUFFICIENCY_WEIGHTS,
  UNCERTAINTY_LAYERS,
  aisCoveragePercent,
  assessEvidenceSufficiency,
  buildForensicAssessment,
  buildHypothesisReplay,
  compareCandidates,
  competingHypotheses,
  contradictingFactors,
  investigationStatus,
  recommendNextEvidence,
  sufficiencyDimensions,
  uncertaintyChain,
} from '../src/lib/forensics.js'
import { DETECTION, INVESTIGATION } from './fixtures/case-001.mjs'

/**
 * Provenance must name an existing API path (or the derived module), matching the
 * convention the evidence chain already uses.
 */
const SOURCE_SHAPE = /^(detection|origin|investigation|ranking|trajectory|forensics|not-integrated)(\b|\.|\[|,| |:)/

const TOP = INVESTIGATION.ranking.entries.find((e) => e.mmsi === '900000001')
const LOW = INVESTIGATION.ranking.entries.find((e) => e.mmsi === '900000005')
const NEAREST_ONLY = INVESTIGATION.ranking.entries.find((e) => e.mmsi === '900000004')

/** Every string reachable from a result, for whole-output assertions. */
function stringsIn(value, out = []) {
  if (typeof value === 'string') out.push(value)
  else if (Array.isArray(value)) for (const item of value) stringsIn(item, out)
  else if (value && typeof value === 'object') for (const item of Object.values(value)) stringsIn(item, out)
  return out
}

/** Everything the UI could render, to prove no NaN/undefined leaks out. */
function audit(value, acc = { nums: [], sources: [], undefineds: [] }) {
  if (typeof value === 'number') acc.nums.push(value)
  else if (value === undefined) acc.undefineds.push('undefined')
  else if (Array.isArray(value)) for (const item of value) audit(item, acc)
  else if (value && typeof value === 'object') {
    for (const [key, item] of Object.entries(value)) {
      if (key === 'source' && typeof item === 'string') acc.sources.push(item)
      audit(item, acc)
    }
  }
  return acc
}

/** A candidate fixture whose named factors are zeroed. */
function withZeroedFactors(entry, keys) {
  const factors = { ...entry.factors }
  for (const key of keys) factors[key] = { ...factors[key], points: 0 }
  return { ...entry, factors }
}

/** The investigation payload with one ranking entry replaced. */
function withEntry(replacement) {
  return {
    ...INVESTIGATION,
    ranking: {
      ...INVESTIGATION.ranking,
      entries: INVESTIGATION.ranking.entries.map((e) => (e.mmsi === replacement.mmsi ? replacement : e)),
    },
  }
}

/* --------------------------------------------- Feature 1: sufficiency gate */

test('CASE-001 top candidate reads as HIGH evidence compatibility, not forced down', () => {
  const assessment = assessEvidenceSufficiency({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP })
  assert.equal(assessment.status, SUFFICIENCY.HIGH)
  assert.equal(assessment.tone, 'ok')
  assert.equal(assessment.composite, 87.5)
  assert.equal(assessment.isProbability, false)
  assert.equal(assessment.contradictions.length, 0)
  assert.equal(assessment.missingCritical.length, 0)
})

test('both ends of the band scale are reachable from real CASE-001 data', () => {
  const statuses = INVESTIGATION.ranking.entries.map(
    (entry) => assessEvidenceSufficiency({ investigation: INVESTIGATION, detection: DETECTION, candidate: entry }).status,
  )
  assert.ok(statuses.includes(SUFFICIENCY.HIGH), 'HIGH must occur for the leading candidates')
  assert.ok(statuses.includes(SUFFICIENCY.INSUFFICIENT), 'INSUFFICIENT must occur for the uncorrelated candidates')
  for (const entry of INVESTIGATION.ranking.entries) {
    const assessment = assessEvidenceSufficiency({ investigation: INVESTIGATION, detection: DETECTION, candidate: entry })
    if (assessment.status === SUFFICIENCY.HIGH) assert.ok(assessment.composite >= SUFFICIENCY_THRESHOLDS.high)
  }
})

test('a partially-compatible candidate reads as MODERATE evidence compatibility', () => {
  const partial = withZeroedFactors(TOP, ['spatial', 'trajectory'])
  const assessment = assessEvidenceSufficiency({ investigation: INVESTIGATION, detection: DETECTION, candidate: partial })
  assert.equal(assessment.status, SUFFICIENCY.MODERATE)
  assert.equal(assessment.tone, 'warn')
  assert.ok(assessment.composite >= SUFFICIENCY_THRESHOLDS.moderate)
  assert.ok(assessment.composite < SUFFICIENCY_THRESHOLDS.high)
  assert.match(assessment.explanation, /Additional corroborating evidence is recommended\./)
})

test('a candidate with no compatible evidence reads as INSUFFICIENT', () => {
  const assessment = assessEvidenceSufficiency({ investigation: INVESTIGATION, detection: DETECTION, candidate: LOW })
  assert.equal(assessment.status, SUFFICIENCY.INSUFFICIENT)
  assert.equal(assessment.tone, 'danger')
  assert.ok(assessment.composite < SUFFICIENCY_THRESHOLDS.moderate)
  assert.ok(assessment.contradictions.length > 0)
})

test('a missing critical input yields INSUFFICIENT rather than a deflated guess', () => {
  const assessment = assessEvidenceSufficiency({
    investigation: INVESTIGATION,
    detection: { ...DETECTION, detectionConfidence: null },
    candidate: TOP,
  })
  assert.equal(assessment.status, SUFFICIENCY.INSUFFICIENT)
  assert.equal(assessment.missingCritical.length, 1)
  assert.match(assessment.missingCritical[0].label, /Detection/)
  const detectionDimension = assessment.dimensions.find((d) => d.key === 'detection')
  assert.equal(detectionDimension.available, false)
  assert.equal(detectionDimension.display, 'Not available')
  // The unavailable dimension is re-normalised out, not counted as a zero.
  assert.equal(assessment.composite, 87.1)
})

test('a missing origin confidence is treated as a critical gap too', () => {
  const trimmed = {
    ...INVESTIGATION,
    origin: { ...INVESTIGATION.origin, region: { ...INVESTIGATION.origin.region, confidence: undefined } },
  }
  const assessment = assessEvidenceSufficiency({ investigation: trimmed, detection: DETECTION, candidate: TOP })
  assert.equal(assessment.status, SUFFICIENCY.INSUFFICIENT)
  assert.match(assessment.missingCritical[0].label, /Origin/)
})

test('an entirely empty response cannot crash the gate and reports nothing available', () => {
  const assessment = assessEvidenceSufficiency({})
  assert.equal(assessment.status, SUFFICIENCY.INSUFFICIENT)
  assert.equal(assessment.composite, null)
  assert.equal(assessment.compositeDisplay, 'Not available')
  assert.deepEqual(assessment.supporting, [])
  assert.equal(assessment.dimensions.length, 8)
  assert.ok(assessment.dimensions.every((d) => d.available === false))
})


test('too many contradicting factors block the HIGH band even with a strong composite', () => {
  const contradicted = {
    ...TOP,
    compatibility: { ...TOP.compatibility, filters: { spatial: false, temporal: false, trajectory: false } },
  }
  const assessment = assessEvidenceSufficiency({
    investigation: withEntry(contradicted),
    detection: DETECTION,
    candidate: contradicted,
  })
  assert.equal(assessment.contradictions.length, 3)
  assert.equal(assessment.status, SUFFICIENCY.MODERATE)
  assert.ok(assessment.composite >= SUFFICIENCY_THRESHOLDS.high, 'the composite itself is unchanged')
})

test('exactly the allowed number of contradictions still permits HIGH', () => {
  const oneFlag = { ...TOP, compatibility: { ...TOP.compatibility, filters: { ...TOP.compatibility.filters, spatial: false } } }
  const assessment = assessEvidenceSufficiency({ investigation: withEntry(oneFlag), detection: DETECTION, candidate: oneFlag })
  assert.equal(assessment.contradictions.length, SUFFICIENCY_THRESHOLDS.maxContradictionsForHigh)
  assert.equal(assessment.status, SUFFICIENCY.HIGH)
})

test('the absence of an AIS gap is never counted against a candidate', () => {
  assert.equal(TOP.gapAnalysis.hasGap, false)
  assert.deepEqual(contradictingFactors(TOP), [])
  const gap = sufficiencyDimensions({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP }).find((d) => d.key === 'gap')
  assert.equal(gap.role, 'context')
  assert.match(gap.detail, /absence of a gap is not evidence/i)
})

test('an infeasible AIS gap is counted, and a feasible one is not', () => {
  const infeasible = { ...TOP, gapAnalysis: { ...TOP.gapAnalysis, hasGap: true, gapCount: 1, anyFeasible: false } }
  const flagged = contradictingFactors(infeasible)
  assert.equal(flagged.length, 1)
  assert.match(flagged[0].label, /not physically feasible/)
  assert.equal(flagged[0].source, 'ranking[].gapAnalysis.anyFeasible')

  const feasible = { ...TOP, gapAnalysis: { ...TOP.gapAnalysis, hasGap: true, gapCount: 1, anyFeasible: true } }
  assert.deepEqual(contradictingFactors(feasible), [])
  const gap = sufficiencyDimensions({ investigation: INVESTIGATION, detection: DETECTION, candidate: feasible }).find((d) => d.key === 'gap')
  assert.equal(gap.role, 'evidence')
})

test('behaviour carried as context only is observed, not auto-converted to a contradiction', () => {
  const contextOnly = { ...TOP, behaviour: { ...TOP.behaviour, isAnomaly: true, scoredEligible: false } }
  const flagged = contradictingFactors(contextOnly)
  assert.equal(flagged.length, 1)
  assert.match(flagged[0].source, /^ranking\[\]\.behaviour/)
})

test('AIS coverage is derived from the two documented API fields and never guessed', () => {
  assert.equal(aisCoveragePercent(TOP.compatibility, INVESTIGATION.origin.releaseWindow), 100)
  assert.equal(aisCoveragePercent(LOW.compatibility, INVESTIGATION.origin.releaseWindow), 97)
  assert.equal(aisCoveragePercent(undefined, INVESTIGATION.origin.releaseWindow), null)
  assert.equal(aisCoveragePercent(TOP.compatibility, {}), null)
  assert.equal(aisCoveragePercent({ windowCoverageSeconds: 100 }, { durationHours: 0 }), null)
  // A partial window must not silently read as full coverage.
  assert.equal(aisCoveragePercent({ windowCoverageSeconds: 14400 }, { durationHours: 8 }), 50)
})

test('the composite is the declared weighted mean over available dimensions', () => {
  const assessment = assessEvidenceSufficiency({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP })
  const available = assessment.dimensions.filter((d) => d.available)
  const weightSum = available.reduce((s, d) => s + d.weight, 0)
  const expected = available.reduce((s, d) => s + d.percent * d.weight, 0) / weightSum
  assert.equal(assessment.composite, Number(expected.toFixed(1)))
  assert.equal(weightSum, 100)
  assert.equal(Object.values(SUFFICIENCY_WEIGHTS).reduce((a, b) => a + b, 0), 100)
})

test('a dimension is never reported as both supporting and a caution', () => {
  for (const entry of INVESTIGATION.ranking.entries) {
    const assessment = assessEvidenceSufficiency({ investigation: INVESTIGATION, detection: DETECTION, candidate: entry })
    const supportSources = new Set(assessment.supporting.map((s) => s.source))
    for (const caution of assessment.caution) {
      assert.equal(supportSources.has(caution.source), false, `${entry.mmsi}: ${caution.source} is both`)
    }
  }
})

test('origin uncertainty is surfaced as a caution at CASE-001 confidence', () => {
  const assessment = assessEvidenceSufficiency({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP })
  const labels = assessment.caution.map((c) => c.label)
  assert.ok(labels.includes('Origin uncertainty'))
  assert.ok(labels.includes('Behavioural evidence is weak'))
  const supporting = assessment.supporting.map((s) => s.label)
  assert.ok(supporting.includes('Spatial compatibility'))
  assert.ok(supporting.includes('Track alignment'))
  assert.equal(assessment.limiting.label, 'Behaviour evidence')
})

test('the tuning block is a single frozen, documented source of thresholds', () => {
  assert.equal(Object.isFrozen(SUFFICIENCY_THRESHOLDS), true)
  assert.equal(Object.isFrozen(SUFFICIENCY_WEIGHTS), true)
  assert.ok(SUFFICIENCY_THRESHOLDS.high > SUFFICIENCY_THRESHOLDS.moderate)
  for (const key of ['high', 'moderate', 'maxContradictionsForHigh', 'originCautionBelow', 'aisCoverageCautionBelow', 'supportingDimensionPercent']) {
    assert.equal(typeof SUFFICIENCY_THRESHOLDS[key], 'number', `missing threshold ${key}`)
  }
})


/* ------------------------------------------- Feature 2: uncertainty chain */

test('the uncertainty cascade is ordered observation → origin → window → correlation → confidence', () => {
  const chain = uncertaintyChain({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP })
  assert.deepEqual(
    chain.layers.map((l) => l.id),
    UNCERTAINTY_LAYERS.map((l) => l.id),
  )
  assert.deepEqual(chain.layers.map((l) => l.id), ['observation', 'origin', 'window', 'correlation', 'confidence'])
})

test('each uncertainty layer states a value or says Not available, with its source', () => {
  const chain = uncertaintyChain({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP })
  const byId = Object.fromEntries(chain.layers.map((l) => [l.id, l]))
  assert.equal(byId.observation.percent, 91)
  assert.equal(byId.origin.percent, 77)
  assert.equal(byId.correlation.percent, 100)
  assert.equal(byId.confidence.percent, 87.5)
  for (const l of chain.layers) {
    assert.match(l.source, SOURCE_SHAPE, `bad provenance on layer ${l.id}`)
    assert.ok(typeof l.display === 'string' && l.display.length > 0)
    if (!l.available) assert.equal(l.display, 'Not available')
  }
})

test('the release window publishes no confidence, so none is displayed or invented', () => {
  const chain = uncertaintyChain({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP })
  const window = chain.layers.find((l) => l.id === 'window')
  assert.equal(window.percent, null)
  assert.equal(window.available, false)
  assert.equal(window.display, 'Not available')
  assert.equal(window.source, 'origin.releaseWindow')
  assert.match(window.note, /no confidence value/)
  assert.match(window.note, /case-input prior/)
})

test('the API uncertainty radius is surfaced verbatim and never invented', () => {
  const chain = uncertaintyChain({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP })
  assert.equal(chain.radiusKm, 6.776)
  assert.equal(chain.radiusSource, 'origin.region.spreadKm')
  assert.match(chain.radiusDisplay, /^± 6\.776 km internal model spread$/)

  const withoutRadius = {
    ...INVESTIGATION,
    origin: { ...INVESTIGATION.origin, region: { ...INVESTIGATION.origin.region, spreadKm: undefined } },
  }
  const bare = uncertaintyChain({ investigation: withoutRadius, detection: DETECTION, candidate: TOP })
  assert.equal(bare.radiusKm, null)
  assert.equal(bare.radiusDisplay, 'Not available')
})

test('uncertainty is asserted only for layers that actually carry it', () => {
  const chain = uncertaintyChain({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP })
  assert.match(chain.uncertaintyNote, /^Uncertainty remains:/)
  // The observation layer is confident, so it must not be described as uncertain.
  assert.doesNotMatch(chain.uncertaintyNote, /observation/i)

  const bare = uncertaintyChain({})
  assert.match(bare.uncertaintyNote, /Uncertainty remains/)
  assert.equal(bare.layers.every((l) => !l.available), true)
})


/* ----------------------------------------- Feature 3: competing hypotheses */

test('every hypothesis the case can speak to is listed, with evidence for and against', () => {
  const { hypotheses } = competingHypotheses({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP })
  assert.deepEqual(
    hypotheses.map((h) => h.id),
    [HYPOTHESIS_IDS.CANDIDATE, HYPOTHESIS_IDS.LOOK_ALIKE, HYPOTHESIS_IDS.INFRASTRUCTURE, HYPOTHESIS_IDS.UNRESOLVED],
  )
  for (const item of hypotheses) {
    assert.ok(Object.values(HYPOTHESIS_STATUS).includes(item.status), `bad status ${item.status}`)
    assert.ok(Array.isArray(item.supporting) && Array.isArray(item.contradicting))
    assert.ok(typeof item.explanation === 'string' && item.explanation.length > 0)
  }
})

test('the look-alike hypothesis is supported by the classes the API did not assess', () => {
  const { hypotheses } = competingHypotheses({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP })
  const lookAlike = hypotheses.find((h) => h.id === HYPOTHESIS_IDS.LOOK_ALIKE)
  const notAssessed = DETECTION.lookAlikeAssessment.notAssessedClasses
  assert.equal(lookAlike.status, HYPOTHESIS_STATUS.PARTIAL)
  assert.equal(lookAlike.supporting.length, notAssessed.length)
  assert.equal(lookAlike.supporting.length, 3)
  assert.ok(lookAlike.supporting.every((s) => s.source === 'detection.lookAlikeAssessment.notAssessedClasses'))
  assert.equal(lookAlike.contradicting.length, 1)
  assert.match(lookAlike.contradicting[0].label, /Low-wind calm area excluded/)
  assert.match(lookAlike.uncertainty.join(' '), /3 of 4 look-alike classes were not assessed/)
})

test('the look-alike hypothesis leads when the engine raises its own warning', () => {
  const warned = { ...DETECTION, lookAlikeAssessment: { ...DETECTION.lookAlikeAssessment, lookAlikeWarning: true } }
  const { hypotheses } = competingHypotheses({ investigation: INVESTIGATION, detection: warned, candidate: TOP })
  assert.equal(hypotheses.find((h) => h.id === HYPOTHESIS_IDS.LOOK_ALIKE).status, HYPOTHESIS_STATUS.SUPPORTED)
})

test('the look-alike hypothesis is INSUFFICIENT DATA when no assessment was returned', () => {
  const { lookAlikeAssessment, ...bare } = DETECTION
  const { hypotheses } = competingHypotheses({ investigation: INVESTIGATION, detection: bare, candidate: TOP })
  const lookAlike = hypotheses.find((h) => h.id === HYPOTHESIS_IDS.LOOK_ALIKE)
  assert.equal(lookAlike.status, HYPOTHESIS_STATUS.NO_DATA)
  assert.equal(lookAlike.assessable, false)
  assert.deepEqual(lookAlike.supporting, [])
  assert.deepEqual(lookAlike.contradicting, [])
})

test('the infrastructure hypothesis carries zero evidence rather than invented evidence', () => {
  const { hypotheses } = competingHypotheses({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP })
  const infra = hypotheses.find((h) => h.id === HYPOTHESIS_IDS.INFRASTRUCTURE)
  assert.equal(infra.assessable, false)
  assert.equal(infra.status, HYPOTHESIS_STATUS.NO_DATA)
  assert.deepEqual(infra.supporting, [])
  assert.deepEqual(infra.contradicting, [])
  assert.deepEqual(infra.sources, [])
})

test('the unresolved hypothesis strengthens as the evidence weakens', () => {
  const strong = competingHypotheses({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP }).hypotheses
    .find((h) => h.id === HYPOTHESIS_IDS.UNRESOLVED)
  assert.equal(strong.status, HYPOTHESIS_STATUS.PARTIAL)
  assert.ok(strong.supporting.some((s) => /share an identical score/.test(s.label)))

  const weak = competingHypotheses({ investigation: INVESTIGATION, detection: DETECTION, candidate: LOW }).hypotheses
    .find((h) => h.id === HYPOTHESIS_IDS.UNRESOLVED)
  assert.equal(weak.status, HYPOTHESIS_STATUS.SUPPORTED)
})

test('the candidate hypothesis follows the sufficiency band and no hypothesis carries a probability', () => {
  const strong = competingHypotheses({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP })
  assert.equal(strong.hypotheses[0].status, HYPOTHESIS_STATUS.SUPPORTED)
  assert.match(strong.hypotheses[0].explanation, /not a probability that this vessel caused the slick/)

  const weak = competingHypotheses({ investigation: INVESTIGATION, detection: DETECTION, candidate: LOW })
  assert.equal(weak.hypotheses[0].status, HYPOTHESIS_STATUS.WEAK)
  for (const item of [...strong.hypotheses, ...weak.hypotheses]) assert.equal(item.probability, null)
})


/* ------------------------------------------- Feature 4: candidate comparison */

test('two CASE-001 candidates compare axis by axis', () => {
  const comparison = compareCandidates({ investigation: INVESTIGATION, detection: DETECTION, mmsiA: '900000001', mmsiB: '900000004' })
  assert.equal(comparison.available, true)
  assert.equal(comparison.a.mmsi, '900000001')
  assert.equal(comparison.b.mmsi, '900000004')
  assert.deepEqual(
    comparison.axes.map((axis) => axis.key),
    ['totalScore', 'spatial', 'temporal', 'trajectory', 'behaviour', 'gap', 'aisCoverage', 'supporting', 'contradicting', 'uncertainty', 'sufficiency'],
  )
  for (const axis of comparison.axes) {
    assert.match(axis.source, SOURCE_SHAPE, `bad provenance on axis ${axis.key}`)
    assert.ok(typeof axis.label === 'string' && axis.label.length > 0)
  }
})

test('the compared values are the engine’s own, not recomputed', () => {
  const comparison = compareCandidates({ investigation: INVESTIGATION, detection: DETECTION, mmsiA: '900000001', mmsiB: '900000004' })
  const byKey = Object.fromEntries(comparison.axes.map((a) => [a.key, a]))
  assert.equal(byKey.totalScore.a.value, TOP.totalScore)
  assert.equal(byKey.spatial.a.value, TOP.factors.spatial.points)
  assert.equal(byKey.temporal.a.value, TOP.factors.temporal.points)
  assert.equal(byKey.trajectory.a.value, TOP.factors.trajectory.points)
  assert.equal(byKey.behaviour.a.value, TOP.factors.behaviour.points)
  assert.equal(byKey.gap.b.value, NEAREST_ONLY.factors.gap.points)
  assert.equal(byKey.aisCoverage.b.value, 58)
})

test('fewer contradicting factors and less uncertainty count as leads', () => {
  const comparison = compareCandidates({ investigation: INVESTIGATION, detection: DETECTION, mmsiA: '900000001', mmsiB: '900000004' })
  const contradicting = comparison.axes.find((a) => a.key === 'contradicting')
  const uncertainty = comparison.axes.find((a) => a.key === 'uncertainty')
  assert.equal(contradicting.lowerIsBetter, true)
  assert.equal(uncertainty.lowerIsBetter, true)
  // Candidate A has fewer contradictions, so it leads despite the lower number.
  assert.ok(contradicting.a.value < contradicting.b.value)
  assert.equal(contradicting.winner, 'a')
  assert.ok(uncertainty.a.value < uncertainty.b.value)
  assert.equal(uncertainty.winner, 'a')
})

test('the comparison explains why the ranking differs, in compatibility language', () => {
  const comparison = compareCandidates({ investigation: INVESTIGATION, detection: DETECTION, mmsiA: '900000001', mmsiB: '900000004' })
  assert.match(comparison.summary, /ranks/)
  const texts = comparison.aAdvantages.map((a) => a.text)
  assert.ok(texts.includes('stronger spatial compatibility'))
  assert.ok(texts.includes('fewer contradicting factors'))
  assert.ok(comparison.bAdvantages.some((a) => a.text === 'weaker trajectory alignment'))
  assert.equal(comparison.aAdvantages.every((a) => a.tone === 'ok'), true)
  assert.equal(comparison.bAdvantages.some((a) => a.tone === 'muted'), true)
  assert.match(comparison.note, /not responsibility for it/)
})

test('comparing a candidate with itself yields no winners and no invented distinction', () => {
  const comparison = compareCandidates({ investigation: INVESTIGATION, detection: DETECTION, mmsiA: '900000001', mmsiB: '900000001' })
  assert.equal(comparison.available, true)
  assert.ok(comparison.axes.every((axis) => axis.winner === null))
  assert.equal(comparison.leadsOn.decidable, 0)
  assert.deepEqual(comparison.aAdvantages, [])
  assert.deepEqual(comparison.bAdvantages, [])
})

test('an unknown MMSI yields an explicit unavailable comparison, not empty bars', () => {
  const missing = compareCandidates({ investigation: INVESTIGATION, detection: DETECTION, mmsiA: '000000000', mmsiB: '900000004' })
  assert.equal(missing.available, false)
  assert.match(missing.reason, /candidate A/)
  assert.deepEqual(missing.axes, [])
  const both = compareCandidates({ investigation: INVESTIGATION, detection: DETECTION })
  assert.equal(both.available, false)
  assert.match(both.reason, /both candidates/)
})


/* ---------------------------------------------- Feature 5: hypothesis replay */

const TRACK = {
  stats: { recordCount: 425, observedDistanceKm: 380.5, firstTimestamp: '2026-03-11T06:00:00Z' },
  geometry: { type: 'LineString', coordinates: INVESTIGATION.origin.drift.backdriftPath.map(([lat, lon]) => [lon, lat]) },
}

test('the replay reports the reconstruction stages with their provenance', () => {
  const replay = buildHypothesisReplay({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP, trajectory: TRACK })
  assert.equal(replay.available, true)
  assert.deepEqual(replay.stages.map((s) => s.id), ['track', 'origin', 'drift', 'slick', 'forward'])
  for (const stage of replay.stages) {
    assert.match(stage.source, SOURCE_SHAPE, `bad provenance on stage ${stage.id}`)
    assert.ok(typeof stage.display === 'string' && stage.display.length > 0)
  }
  const byId = Object.fromEntries(replay.stages.map((s) => [s.id, s]))
  assert.equal(byId.origin.display, '119.5 km² probable region')
  assert.equal(byId.slick.display, '41.3 km² observed slick')
  assert.equal(byId.drift.display, '41-point modelled path')
  assert.equal(byId.forward.available, false)
})

test('a missing forward drift output is reported honestly and no overlap is claimed', () => {
  const replay = buildHypothesisReplay({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP, trajectory: TRACK })
  assert.equal(replay.forward.available, false)
  assert.equal(replay.forward.overlapAvailable, false)
  assert.equal(replay.forward.message, 'Forward model replay unavailable: no forward drift output was supplied')
  const forwardStage = replay.stages.find((s) => s.id === 'forward')
  assert.equal(forwardStage.display, 'Not available for this case')
  assert.match(forwardStage.note, /no overlap percentage is computed/i)
})

test('a supplied forward footprint is reported as available but still claims no overlap', () => {
  const footprint = { type: 'Polygon', coordinates: [INVESTIGATION.origin.region.geometry.coordinates[0]] }
  const replay = buildHypothesisReplay({
    investigation: INVESTIGATION,
    detection: DETECTION,
    candidate: TOP,
    trajectory: TRACK,
    forecast: { geometry: footprint },
  })
  assert.equal(replay.forward.available, true)
  assert.equal(replay.forward.overlapAvailable, false)
  assert.equal(replay.forward.message, 'Model replay available from existing forecast data')
  assert.match(replay.stages.find((s) => s.id === 'forward').note, /No overlap percentage is computed/)
})

test('the replay answers the consistency question, never the causation question', () => {
  const replay = buildHypothesisReplay({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP, trajectory: TRACK })
  assert.match(replay.question, /^Could this candidate/)
  assert.match(replay.answer, /not proof that it caused the slick/)
  assert.equal(replay.compatibility.summary, '3 of 3 engine checks pass')
  assert.equal(replay.compatibility.checks.length, 3)
  assert.equal(replay.stages.find((s) => s.id === 'drift').available, true)

  const far = buildHypothesisReplay({ investigation: INVESTIGATION, detection: DETECTION, candidate: LOW, trajectory: TRACK })
  assert.match(far.answer, /^Not on every dimension\./)
  assert.ok(far.compatibility.failed.length > 0)
})

test('the replay geometry is normalised to lat/lon for the plot', () => {
  const replay = buildHypothesisReplay({ investigation: INVESTIGATION, detection: DETECTION, candidate: TOP, trajectory: TRACK })
  assert.equal(replay.geo.slick.length, 49)
  assert.equal(replay.geo.origin.length, 36)
  assert.equal(replay.geo.backdrift.length, 41)
  assert.equal(replay.geo.track.length, 41)
  for (const set of [replay.geo.slick, replay.geo.origin, replay.geo.backdrift, replay.geo.track]) {
    for (const point of set) {
      assert.equal(Number.isFinite(point.lat), true)
      assert.equal(Number.isFinite(point.lon), true)
      // The CASE-001 scene is in the Arabian Sea; a swapped ring would land elsewhere.
      assert.ok(point.lat > 17 && point.lat < 19.5, `implausible latitude ${point.lat}`)
      assert.ok(point.lon > 71 && point.lon < 73, `implausible longitude ${point.lon}`)
    }
  }
  assert.ok(replay.framedBounds.minLat < replay.framedBounds.maxLat)
  assert.ok(replay.framedBounds.minLon < replay.framedBounds.maxLon)
})

test('no candidate selected means no replay rather than an empty one', () => {
  const replay = buildHypothesisReplay({ investigation: INVESTIGATION, detection: DETECTION, candidate: null })
  assert.equal(replay.available, false)
  assert.match(replay.reason, /No candidate is selected/)
  assert.deepEqual(replay.stages, [])
})
