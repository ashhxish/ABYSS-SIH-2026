import assert from 'node:assert/strict'
import test from 'node:test'
import { LAYER_ORDER, REASON_PREFIX, buildEvidenceChain, reasonsByFactor } from '../src/lib/evidence.js'
import { EVIDENCE_STATUS } from '../src/lib/timeline.js'
import { DETECTION, INVESTIGATION } from './fixtures/case-001.mjs'

const SOURCE_SHAPE = /^(detection|origin|investigation|ranking|trajectory)(\b|\.|\[)/

test('an unknown or absent selection yields an unavailable chain, not a blank one', () => {
  const missing = buildEvidenceChain(INVESTIGATION, DETECTION, '000000000', null)
  assert.equal(missing.available, false)
  assert.match(missing.reason, /No ranked candidate matches/)
  assert.deepEqual(missing.layers, [])
})

test('the chain uses the method cascade: observed → modelled → correlation → compatibility → ranking', () => {
  const chain = buildEvidenceChain(INVESTIGATION, DETECTION, '900000001', null)
  assert.deepEqual(
    chain.layers.map((layer) => layer.id),
    LAYER_ORDER.map((layer) => layer.id),
  )
  assert.equal(chain.layers[0].nodes.length > 0, true)
  assert.equal(chain.layers[4].nodes.length > 0, true)
})

test('every chain node cites an API source path', () => {
  const chain = buildEvidenceChain(INVESTIGATION, DETECTION, '900000002', null)
  for (const layer of chain.layers) {
    for (const item of layer.nodes) {
      assert.match(item.source, SOURCE_SHAPE, `bad provenance on ${item.id}: ${item.source}`)
    }
  }
})

test('the five factors are passed through unchanged from the API', () => {
  const entry = INVESTIGATION.ranking.entries.find((e) => e.mmsi === '900000001')
  const chain = buildEvidenceChain(INVESTIGATION, DETECTION, '900000001', null)
  assert.equal(chain.totalScore, entry.totalScore)
  assert.equal(chain.totalScore, 83.564)
  assert.equal(chain.rank, 1)
  const byKey = Object.fromEntries(chain.factors.map((f) => [f.factorKey, f]))
  assert.deepEqual(Object.keys(byKey).sort(), ['behaviour', 'gap', 'spatial', 'temporal', 'trajectory'])
  assert.equal(byKey.spatial.points, 35)
  assert.equal(byKey.temporal.points, 25)
  assert.equal(byKey.trajectory.points, 20)
  assert.equal(byKey.behaviour.points, 3.564)
  assert.equal(byKey.gap.points, 0)
  for (const key of Object.keys(byKey)) {
    assert.equal(byKey[key].maxPoints, entry.factors[key].maxPoints)
  }
})

test('every factor of every candidate carries the engine’s own explanation', () => {
  const unresolved = []
  for (const entry of INVESTIGATION.ranking.entries) {
    const chain = buildEvidenceChain(INVESTIGATION, DETECTION, entry.mmsi, null)
    for (const factor of chain.factors) {
      if (!REASON_PREFIX[factor.factorKey]) {
        unresolved.push(`${entry.vesselId}:${factor.factorKey}:no-prefix`)
      } else if (/returned no reason string/.test(factor.summary)) {
        unresolved.push(`${entry.vesselId}:${factor.factorKey}`)
      }
    }
  }
  assert.deepEqual(unresolved, [])
})

test('reasonsByFactor maps engine strings onto the right factors', () => {
  const mapped = reasonsByFactor([
    'distance to origin region: inside the estimated origin region during the window [35/35]',
    'AIS-gap behaviour: no AIS gap [0/10]',
    'course-change correlation: plausible [20/20]',
    'stop/slow pattern: own-baseline anomaly 0.36 [3.564/10]',
    'proximity to release window: present [25/25]',
  ])
  assert.match(mapped.spatial, /^distance to origin region/)
  assert.match(mapped.gap, /^AIS-gap behaviour/)
  assert.match(mapped.trajectory, /^course-change correlation/)
  assert.match(mapped.behaviour, /^stop\/slow pattern/)
  assert.match(mapped.temporal, /^proximity to release window/)
})

test('the feasible V002 gap and the infeasible V003 gap are explained differently', () => {
  const feasible = buildEvidenceChain(INVESTIGATION, DETECTION, '900000002', null).factors.find(
    (f) => f.factorKey === 'gap',
  )
  const infeasible = buildEvidenceChain(INVESTIGATION, DETECTION, '900000003', null).factors.find(
    (f) => f.factorKey === 'gap',
  )
  assert.equal(feasible.points, 3)
  assert.match(feasible.summary, /traversable at 10\.5 kn/)
  assert.equal(infeasible.points, 0)
  assert.match(infeasible.summary, /impossible to traverse \(35\.1 kn required vs 15\.9 kn cap\)/)
})

test('the counterfactual is the engine’s own string and deltas', () => {
  const chain = buildEvidenceChain(INVESTIGATION, DETECTION, '900000001', null)
  assert.equal(chain.counterfactual.available, true)
  assert.equal(chain.counterfactual.againstName, 'DEMO HARBOUR LIGHT')
  assert.match(chain.counterfactual.text, /nearest to the observed slick \(1\.1 km\)/)
  assert.equal(chain.counterfactual.deltas.spatial, 35)
  const node = chain.layers[4].nodes.find((n) => n.id === 'n-counterfactual')
  assert.equal(node.available, true)
  assert.match(node.title, /Why not DEMO HARBOUR LIGHT\?/)
})

test('a missing counterfactual renders the exact fallback wording', () => {
  const trimmed = {
    ...INVESTIGATION,
    ranking: {
      ...INVESTIGATION.ranking,
      entries: INVESTIGATION.ranking.entries.map((entry) =>
        entry.mmsi === '900000001' ? { ...entry, counterfactual: undefined } : entry,
      ),
    },
  }
  const chain = buildEvidenceChain(trimmed, DETECTION, '900000001', null)
  assert.equal(chain.counterfactual.available, false)
  const node = chain.layers[4].nodes.find((n) => n.id === 'n-counterfactual')
  assert.equal(node.unavailableReason, 'Counterfactual comparison unavailable.')
})

test('the track node reports unavailability instead of an invented track', () => {
  const withoutBundle = buildEvidenceChain(INVESTIGATION, DETECTION, '900000001', null)
  const missing = withoutBundle.layers[2].nodes.find((n) => n.id === 'n-track')
  assert.equal(missing.available, false)
  assert.match(missing.unavailableReason, /not loaded for this vessel/)

  const withBundle = buildEvidenceChain(INVESTIGATION, DETECTION, '900000001', {
    stats: { recordCount: 425, firstTimestamp: '2026-03-11T06:00:00Z', observedDistanceKm: 380.5 },
  })
  const track = withBundle.layers[2].nodes.find((n) => n.id === 'n-track')
  assert.equal(track.available, true)
  const byLabel = Object.fromEntries(track.metrics.map((m) => [m.label, m.value]))
  assert.equal(byLabel.Positions, '425')
  assert.equal(byLabel['Observed distance'], '380.5 km')
})

test('the release-window node is PRIOR, so modelled layers are not overstated', () => {
  const chain = buildEvidenceChain(INVESTIGATION, DETECTION, '900000001', null)
  const modelled = chain.layers.find((layer) => layer.id === 'modelled')
  const windowNode = modelled.nodes.find((n) => n.id === 'n-window')
  const driftNode = modelled.nodes.find((n) => n.id === 'n-drift')
  assert.equal(windowNode.status, EVIDENCE_STATUS.PRIOR)
  assert.equal(driftNode.status, EVIDENCE_STATUS.MODELLED)
})

test('the narrative is neutral, ordinal and free of responsibility claims', () => {
  const chain = buildEvidenceChain(INVESTIGATION, DETECTION, '900000002', null)
  const text = chain.narrative.join(' ')
  assert.match(text, /investigation priority/)
  assert.match(text, /gap is physically feasible/)
  assert.match(text, /supplied as a case-input prior/)
  // The explicit disclaimer must be present...
  assert.match(text, /not a probability of responsibility/)
  // ...and once removed, no affirmative responsibility claim may remain.
  const withoutDisclaimers = text
    .replace(/not a probability of responsibility/gi, '')
    .replace(/not proof of anything/gi, '')
  assert.doesNotMatch(
    withoutDisclaimers.toLowerCase(),
    /guilty|culprit|confirmed responsible|probable cause|probability of guilt|probability of responsibility/,
  )

  const infeasible = buildEvidenceChain(INVESTIGATION, DETECTION, '900000003', null)
    .narrative.join(' ')
  assert.match(infeasible, /not physically feasible/)
})

test('building the chain twice yields identical output', () => {
  const a = buildEvidenceChain(INVESTIGATION, DETECTION, '900000003', null)
  const b = buildEvidenceChain(INVESTIGATION, DETECTION, '900000003', null)
  assert.deepEqual(a, b)
})

