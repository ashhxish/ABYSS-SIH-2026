import assert from 'node:assert/strict'
import test from 'node:test'
import {
  EVIDENCE_STATUS,
  SOURCE,
  buildTimeline,
  countByStatus,
  isEmphasised,
  parseIso,
  summariseTimeline,
  timelineRange,
} from '../src/lib/timeline.js'
import { DETECTION, INVESTIGATION } from './fixtures/case-001.mjs'

const KNOWN_SOURCES = new Set(Object.values(SOURCE))

test('every timeline event cites a known API source path', () => {
  const { events } = buildTimeline(INVESTIGATION, DETECTION)
  assert.ok(events.length > 20, `expected a populated timeline, got ${events.length}`)
  for (const event of events) {
    assert.ok(KNOWN_SOURCES.has(event.source), `unexpected provenance: ${event.source}`)
  }
})

test('no timestamp is ever invented: timed events parse, others stay untimed', () => {
  const { events, timed, untimed } = buildTimeline(INVESTIGATION, DETECTION)
  assert.equal(timed.length + untimed.length, events.length)
  for (const event of timed) {
    assert.notEqual(parseIso(event.at), null, `unparsable timestamp on ${event.id}`)
  }
  for (const event of untimed) {
    assert.equal(event.at, null)
  }
})

test('the timeline is chronological, ascending, ties broken deterministically', () => {
  const { timed } = buildTimeline(INVESTIGATION, DETECTION)
  const times = timed.map((event) => parseIso(event.at))
  assert.deepEqual(times, [...times].sort((a, b) => a - b))
})

test('building the timeline twice yields identical output', () => {
  assert.deepEqual(buildTimeline(INVESTIGATION, DETECTION), buildTimeline(INVESTIGATION, DETECTION))
})

test('the release window is shown as a case-input PRIOR, never as a derived result', () => {
  const { events } = buildTimeline(INVESTIGATION, DETECTION)
  const step = events.find((event) => event.id === 'release-window')
  assert.equal(step.status, EVIDENCE_STATUS.PRIOR)
  assert.equal(step.at, INVESTIGATION.origin.releaseWindow.start)
  assert.equal(step.end, INVESTIGATION.origin.releaseWindow.end)
  assert.match(step.description, /not derived from the slick/)
})

test('satellite observation carries the API acquisition time and confidence', () => {
  const { events } = buildTimeline(INVESTIGATION, DETECTION)
  const observed = events.find((event) => event.id === 'satellite-observation')
  assert.equal(observed.at, DETECTION.acquisitionTime)
  assert.equal(observed.status, EVIDENCE_STATUS.OBSERVED)
  assert.equal(observed.confidence, DETECTION.detectionConfidence)
})

test('slick characterisation metrics equal the API characterisation values', () => {
  const { events } = buildTimeline(INVESTIGATION, DETECTION)
  const slick = events.find((event) => event.id === 'slick-characterisation')
  const byLabel = Object.fromEntries(slick.metrics.map((m) => [m.label, m.value]))
  assert.equal(byLabel.Area, `${DETECTION.characterisation.areaKm2.toFixed(2)} km²`)
  assert.equal(byLabel.Length, `${DETECTION.characterisation.approximateLengthKm.toFixed(1)} km`)
  assert.equal(byLabel.Vertices, String(DETECTION.characterisation.vertexCount))
})

test('the origin region event reports region area, vertices and model confidence', () => {
  const { events } = buildTimeline(INVESTIGATION, DETECTION)
  const region = events.find((event) => event.id === 'origin-region')
  assert.equal(region.status, EVIDENCE_STATUS.MODELLED)
  assert.equal(region.confidence, 0.774)
  const byLabel = Object.fromEntries(region.metrics.map((m) => [m.label, m.value]))
  assert.equal(byLabel.Area, '119.5 km²')
  assert.equal(byLabel.Vertices, '36')
})

test('the V002 gap appears with the API start/end and is marked feasible', () => {
  const { events } = buildTimeline(INVESTIGATION, DETECTION)
  const gap = events.find((event) => event.id === '900000002-gap-0')
  assert.ok(gap, 'expected the V002 gap event')
  assert.equal(gap.at, '2026-03-13T11:55:00Z')
  assert.equal(gap.end, '2026-03-13T16:00:00Z')
  const byLabel = Object.fromEntries(gap.metrics.map((m) => [m.label, m.value]))
  assert.equal(byLabel['Physically feasible'], 'yes')
  assert.equal(byLabel['Implied speed'], '10.5 kn')
})

test('the V003 gap is reported as not physically feasible', () => {
  const { events } = buildTimeline(INVESTIGATION, DETECTION)
  const gap = events.find((event) => event.id === '900000003-gap-0')
  const byLabel = Object.fromEntries(gap.metrics.map((m) => [m.label, m.value]))
  assert.equal(byLabel['Physically feasible'], 'no')
  assert.equal(byLabel['Implied speed'], '35.1 kn')
  assert.equal(byLabel['Own speed cap'], '15.9 kn')
})

test('a vessel with no gap gets no fabricated gap event', () => {
  const { events } = buildTimeline(INVESTIGATION, DETECTION)
  assert.equal(
    events.some((event) => event.id.startsWith('900000001-gap')),
    false,
  )
})

test('behavioural events are untimed rather than given an invented time', () => {
  const { events, untimed } = buildTimeline(INVESTIGATION, DETECTION)
  const flagged = events.filter((event) => event.id.endsWith('-behaviour'))
  assert.ok(flagged.length > 0)
  for (const event of flagged) {
    assert.equal(event.at, null)
    assert.ok(untimed.includes(event))
  }
})

test('pipeline steps without timestamps are listed separately', () => {
  const { untimed } = buildTimeline(INVESTIGATION, DETECTION)
  const ids = untimed.map((event) => event.id)
  for (const id of ['ais-filtering', 'evidence-scoring', 'candidate-ranking']) {
    assert.ok(ids.includes(id), `missing untimed step ${id}`)
  }
})

test('isEmphasised keeps case events and the selected vessel, dims the rest', () => {
  const { events } = buildTimeline(INVESTIGATION, DETECTION)
  const caseEvent = events.find((event) => event.scope === 'case')
  const mine = events.find((event) => event.mmsi === '900000001')
  const other = events.find((event) => event.mmsi === '900000005')
  assert.equal(isEmphasised(caseEvent, '900000001'), true)
  assert.equal(isEmphasised(mine, '900000001'), true)
  assert.equal(isEmphasised(other, '900000001'), false)
})

test('the summary narrative is built from API values and avoids causal language', () => {
  const lines = summariseTimeline(INVESTIGATION).join(' ')
  assert.match(lines, /119\.5 km²/)
  assert.match(lines, /3666 cleaned AIS reports/)
  assert.match(lines, /DEMO MERIDIAN STAR/)
  assert.match(lines, /not a probability of responsibility/)
  assert.match(lines, /case-input prior/)
  assert.doesNotMatch(lines.toLowerCase(), /guilty|culprit|confirmed responsible|probability of guilt/)
})

test('timelineRange spans the recorded window and counts by status', () => {
  const timeline = buildTimeline(INVESTIGATION, DETECTION)
  assert.equal(timelineRange(timeline).spanHours, 24.08)
  const counts = countByStatus(timeline)
  assert.equal(counts.OBSERVED + counts.PRIOR + counts.MODELLED + counts.ANALYTICAL, timeline.events.length)
  assert.equal(counts.PRIOR, 1)
})

test('an empty investigation produces no events rather than placeholder ones', () => {
  const timeline = buildTimeline(null, null)
  assert.deepEqual(timeline.events, [])
  assert.deepEqual(timeline.timed, [])
  assert.deepEqual(summariseTimeline(null), [])
})

