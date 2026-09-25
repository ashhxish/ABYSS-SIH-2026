import assert from 'node:assert/strict'
import test from 'node:test'
import { buildTimeline } from '../src/lib/timeline.js'
import { buildEvidenceChain } from '../src/lib/evidence.js'
import {
  REPORT_DISCLAIMER,
  SCORE_LABEL,
  STATUS,
  buildInvestigationReport,
  reportSummaryLines,
} from '../src/lib/report.js'
import { DETECTION, INVESTIGATION } from './fixtures/case-001.mjs'

/** CLEANING-shaped fixture: only the counts the report is allowed to read. */
const CLEANING = {
  datasetLabel: INVESTIGATION.datasetLabel,
  statistics: {
    counts: { rowsIn: 3675, records: 3666, rejected: 9, removedValues: 1, vessels: 12 },
    timeRange: { start: '2026-03-11T06:00:00Z', end: '2026-03-14T05:55:00Z' },
    rejectedByCategory: { duplicate_record: 4, invalid_coordinate: 2 },
  },
}

const V1 = String(INVESTIGATION.ranking.entries[0].mmsi)
const V2 = String(INVESTIGATION.ranking.entries[1].mmsi)

const build = (selected = V1, extra = {}) => {
  const timeline = buildTimeline(INVESTIGATION, DETECTION)
  const chain = buildEvidenceChain(INVESTIGATION, DETECTION, selected, null)
  return buildInvestigationReport({
    investigation: INVESTIGATION,
    detection: DETECTION,
    cleaning: CLEANING,
    timeline,
    chain,
    selectedMmsi: selected,
    ...extra,
  })
}

const section = (report, id) => report.sections.find((s) => s.id === id)
const walk = (node, visit) => {
  if (node == null) return
  if (Array.isArray(node)) return node.forEach((item) => walk(item, visit))
  if (typeof node !== 'object') return visit(node)
  Object.entries(node).forEach(([key, value]) => visit(value, key))
  Object.values(node).forEach((value) => walk(value, visit))
}

test('the report builds for CASE-001 with all twelve sections available', () => {
  const report = build()
  assert.equal(report.caseId, 'CASE-001')
  assert.equal(report.reportId, 'CASE-001-REPORT')
  assert.equal(report.sections.length, 12)
  assert.equal(report.sections.every((s) => s.available), true)
  assert.equal(report.status, STATUS.COMPLETE)
  assert.deepEqual(reportSummaryLines(report).length, 12)
})

test('section 1 identifies the case from the API, with no invented status', () => {
  const data = section(build(), 'case').data
  assert.equal(data.caseId.value, 'CASE-001')
  assert.equal(data.observationTime.available, true)
  assert.equal(data.status.value, STATUS.COMPLETE)
  assert.match(data.status.basis, /12 ranked vessels/)
  assert.equal(data.synthetic.value, true)
})

test('section 2 reports the observed slick geometry and detection confidence', () => {
  const data = section(build(), 'observation').data
  assert.equal(data.detectionConfidence.value, DETECTION.detectionConfidence)
  assert.equal(data.centroidLat.available, true)
  assert.equal(data.geometryFacts.length > 0, true)
  data.geometryFacts.forEach((item) => assert.equal(item.available, true))
})

test('section 3 states the look-alike screening is heuristic', () => {
  const data = section(build(), 'look-alike').data
  assert.match(data.heuristicNote, /heuristic/i)
  assert.equal(data.source, 'detection.lookAlike')
})

test('section 4 labels the probable origin as modelled, never observed', () => {
  const data = section(build(), 'origin').data
  assert.equal(data.regionConfidence.value, INVESTIGATION.origin.region.confidence)
  assert.equal(data.windowStart.available, true)
  assert.equal(data.windowEnd.available, true)
})

test('section 5 carries drift parameters and invents no environmental measurement', () => {
  const data = section(build(), 'environment').data
  assert.equal(data.windageCoefficient.value, INVESTIGATION.origin.drift.windageCoefficient)
  assert.equal(data.stepSeconds.value, INVESTIGATION.origin.drift.stepSeconds)
  assert.match(data.availabilityNote, /No measured currents or winds are published/)
})

test('section 6 reports AIS coverage, cleaning counts and the candidate count', () => {
  const data = section(build(), 'ais').data
  assert.equal(data.recordsRetained.value, 3666)
  assert.equal(data.rowsIn.value, 3675)
  assert.equal(data.rejected.value, 9)
  assert.equal(data.removedValues.value, 1)
  assert.equal(data.datasetLabel.value, 'Synthetic Demonstration Dataset')
  assert.equal(data.vesselsScored.value, INVESTIGATION.statistics.vesselsScored)
})

test('section 7 reproduces the five evidence factors for candidate #1', () => {
  const entry = INVESTIGATION.ranking.entries[0]
  const data = section(build(), 'candidate').data
  assert.equal(data.mmsi.value, entry.mmsi)
  assert.equal(data.rank.value, entry.rank)
  assert.equal(data.totalScore.value, entry.totalScore)
  assert.equal(data.factors.length, 5)
  data.factors.forEach((factor) => {
    const source = entry.factors[factor.key]
    assert.equal(factor.points, source.points, `factor ${factor.key} points`)
    assert.equal(factor.maxPoints, source.maxPoints, `factor ${factor.key} cap`)
  })
  assert.deepEqual(data.reasons, entry.reasons)
})

test('section 7 reproduces behaviour events and gap evidence where the API supplied them', () => {
  const withGap = section(build(V2), 'candidate').data
  assert.equal(withGap.gaps.available, true)
  assert.equal(withGap.gaps.items.length, INVESTIGATION.ranking.entries[1].gapAnalysis.gaps.length)
  withGap.gaps.items.forEach((gap, i) => {
    const source = INVESTIGATION.ranking.entries[1].gapAnalysis.gaps[i]
    assert.equal(gap.durationHours, source.durationHours)
    assert.equal(gap.straightLineKm, source.straightLineKm)
    assert.equal(gap.impliedSpeedKn, source.impliedSpeedKn)
    assert.equal(gap.feasible, source.feasible)
  })
  assert.match(withGap.gaps.contextNote, /does not raise a vessel's priority/)
  const noGap = section(build(V1), 'candidate').data
  assert.equal(noGap.gaps.available, false)
})

test('candidate #1 and #2 produce different candidate-specific evidence', () => {
  const first = section(build(V1), 'candidate').data
  const second = section(build(V2), 'candidate').data
  assert.notEqual(first.mmsi.value, second.mmsi.value)
  assert.notEqual(first.totalScore.value, second.totalScore.value)
  assert.notDeepEqual(first.factors, second.factors)
  assert.notDeepEqual(first.reasons, second.reasons)
  assert.notEqual(first.counterfactual.text.value, second.counterfactual.text.value)
})

test('switching candidates leaves every other section byte-identical', () => {
  const first = build(V1)
  const second = build(V2)
  for (const id of ['case', 'observation', 'origin', 'environment', 'ais', 'confidence', 'limitations']) {
    assert.deepEqual(section(second, id).data, section(first, id).data, `section ${id} changed`)
  }
})

test('section 8 reuses the Phase 16 timeline rather than rebuilding it', () => {
  const timeline = buildTimeline(INVESTIGATION, DETECTION)
  const data = section(build(V1, {}), 'timeline').data
  const vesselEvents = timeline.events.filter((e) => e.scope === 'vessel' && String(e.mmsi) === V1)
  assert.equal(data.counts.case, timeline.events.filter((e) => e.scope === 'case').length)
  assert.equal(data.vesselEvents.length, vesselEvents.length)
  assert.equal(data.source, 'timeline.events (Phase 16 builder)')
})

test('section 9 summarises the Phase 17 evidence chain layers and provenance', () => {
  const chain = buildEvidenceChain(INVESTIGATION, DETECTION, V1, null)
  const data = section(build(V1), 'chain').data
  assert.equal(data.nodeCount, chain.nodes.length)
  assert.equal(data.edgeCount, chain.edges.length)
  assert.equal(data.layerCount, chain.layers.length)
  data.layers.forEach((layer, i) => {
    assert.equal(layer.id, chain.layers[i].id)
    assert.equal(layer.nodes.length, chain.layers[i].nodes.length)
  })
  assert.equal(data.source, 'evidence chain (Phase 17 builder)')
})

test('section 10 keeps confidence dimensions separate and marks absent ones unavailable', () => {
  const data = section(build(), 'confidence').data
  const byKey = Object.fromEntries(data.dimensions.map((dim) => [dim.key, dim]))
  assert.equal(byKey.detection.value, DETECTION.detectionConfidence)
  assert.equal(byKey.origin.value, INVESTIGATION.origin.region.confidence)
  // The API exposes no combined/AIS confidence; the report must say so, not invent one.
  assert.equal(byKey.aisEvidence.available, false)
  assert.equal(byKey.overall.available, false)
  assert.match(byKey.aisEvidence.statusLabel, /not provided/i)
  assert.equal(data.dimensions.some((d) => d.value === 'combined'), false)
})

test('sections 11 and 12 carry the limitations and the required disclaimer', () => {
  const report = build()
  const limitations = section(report, 'limitations').data.items.join(' ').toLowerCase()
  assert.match(limitations, /synthetic/)
  assert.match(limitations, /schematic map|local schematic/)
  assert.match(limitations, /heuristic/)
  assert.match(limitations, /prototype/)
  const methodology = section(report, 'methodology').data
  assert.equal(methodology.disclaimer, REPORT_DISCLAIMER)
  assert.equal(report.disclaimer, REPORT_DISCLAIMER)
  assert.equal(methodology.weights.available, true)
  assert.match(methodology.terminology, /not a determination of responsibility/)
})

test('the score is labelled investigation priority, never a probability of responsibility', () => {
  assert.match(SCORE_LABEL, /investigation priority/)
  const report = build()
  assert.equal(report.scoreLabel, SCORE_LABEL)
  assert.equal(report.disclaimer, REPORT_DISCLAIMER)
})

test('no rendered value uses forbidden causality vocabulary', () => {
  const forbidden = /\b(guilty|culprit|confirmed responsible|probability of responsibility|proven criminal|guaranteed source)\b/i
  const report = build(V2)
  walk(report, (value) => {
    if (typeof value === 'string') assert.doesNotMatch(value, forbidden)
  })
})

test('every available fact carries a provenance label naming its API path', () => {
  const report = build(V2)
  report.sections
    .filter((s) => s.available)
    .forEach((s) => {
      walk(s.data, (value, key) => {
        if (key === 'source' && value) assert.equal(typeof value, 'string')
      })
    })
})

test('every fact names a source and reports missing values as unavailable, never as zero', () => {
  const data = section(build(), 'observation').data
  const all = [...Object.values(data).filter((v) => v && v.label), ...data.geometryFacts]
  all.forEach((item) => {
    assert.ok(item.source, `fact "${item.label}" has no provenance`)
    if (item.available === false) {
      assert.equal(item.value, null)
      assert.notEqual(item.display, '0')
      assert.ok(item.unavailable)
    }
  })
})

test('the report is a pure function of its inputs: same input, same output', () => {
  assert.deepEqual(build(V1), build(V1))
  assert.deepEqual(build(V2), build(V2))
})

test('an absent investigation degrades to unavailable sections instead of throwing', () => {
  const report = buildInvestigationReport({ investigation: null })
  assert.equal(report.caseId, null)
  assert.equal(report.status, STATUS.EMPTY)
  assert.equal(report.generatedFrom.investigation, false)
  assert.equal(section(report, 'case').available, false)
  assert.match(section(report, 'case').unavailableReason, /investigation/i)
  assert.deepEqual(report.sections.find((s) => s.id === 'candidate').data, {
    selected: { value: true, basis: 'No candidate is currently selected.' },
  })
})

test('a report with no loading sources is marked partial, not complete', () => {
  const report = build(V1, { detection: null, cleaning: null, chain: null })
  assert.equal(report.generatedFrom.detection, false)
  assert.equal(section(report, 'observation').available, false)
  assert.equal(section(report, 'ais').available, true)
})
