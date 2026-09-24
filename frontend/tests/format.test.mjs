import assert from 'node:assert/strict'
import test from 'node:test'
import {
  factorRows,
  findCandidate,
  findTrajectory,
  fmtDateTime,
  fmtDuration,
  fmtInt,
  fmtKm,
  fmtNumber,
  fmtPercent,
  rankingEntries,
  scoreBand,
  summariseList,
} from '../src/lib/format.js'

test('factorRows preserves API points and distinguishes zero from unavailable', () => {
  const rows = factorRows({
    spatial: { points: 35, maxPoints: 35, detail: { minDistanceKmDuringWindow: 0 } },
    gap: { points: 0, maxPoints: 10 },
  })
  assert.equal(rows.length, 5, 'all five factors are always shown')
  assert.equal(rows[0].key, 'spatial')
  assert.equal(rows[0].percent, 1)
  assert.equal(rows[0].available, true)
  assert.equal(rows[0].detail.minDistanceKmDuringWindow, 0)

  const gap = rows.find((r) => r.key === 'gap')
  assert.equal(gap.percent, 0)
  assert.equal(gap.available, true, 'a zero-point factor is still available evidence')

  const missing = rows.find((r) => r.key === 'temporal')
  assert.equal(missing.points, 0)
  assert.equal(missing.percent, 0)
  assert.equal(missing.available, false)
  assert.equal(factorRows(null).length, 5)
})

test('numeric formatters never print NaN or null', () => {
  assert.equal(fmtNumber(83.564, 1), '83.6')
  assert.equal(fmtNumber(0, 0), '0')
  assert.equal(fmtNumber(null), '—')
  assert.equal(fmtNumber(undefined), '—')
  assert.equal(fmtNumber('nope'), '—')
  assert.equal(fmtInt(3666), '3,666')
  assert.equal(fmtInt(null), '—')
  assert.equal(fmtKm(0.04, 1), '0.0 km')
  assert.equal(fmtKm(null), '—')
  assert.equal(fmtPercent(0.774, 0), '77%')
  assert.equal(fmtPercent(null), '—')
})

test('fmtDuration formats hours, minutes and seconds', () => {
  assert.equal(fmtDuration(28800), '8h 00m')
  assert.equal(fmtDuration(15600), '4h 20m')
  assert.equal(fmtDuration(125), '2m 05s')
  assert.equal(fmtDuration(42), '42s')
  assert.equal(fmtDuration(null), '—')
})

test('fmtDateTime renders UTC and tolerates junk', () => {
  assert.equal(fmtDateTime('2026-03-14T06:00:00Z'), '14 Mar 2026 06:00 UTC')
  assert.equal(fmtDateTime('not-a-date'), 'not-a-date')
  assert.equal(fmtDateTime(null), '—')
})

test('scoreBand never reads as a probability', () => {
  assert.equal(scoreBand(83.564).label, 'strong evidence')
  assert.equal(scoreBand(45).label, 'moderate evidence')
  assert.equal(scoreBand(3).label, 'weak evidence')
  assert.equal(scoreBand(0).label, 'no scoring evidence')
  assert.equal(scoreBand(null).label, 'unscored')
})

test('ranking helpers find entries and trajectories by string MMSI', () => {
  const investigation = {
    ranking: { entries: [{ mmsi: '900000001', name: 'DEMO MERIDIAN STAR' }] },
  }
  assert.equal(rankingEntries(investigation).length, 1)
  assert.equal(rankingEntries(null).length, 0)
  assert.equal(findCandidate(investigation, '900000001').name, 'DEMO MERIDIAN STAR')
  assert.equal(findCandidate(investigation, 900000001).name, 'DEMO MERIDIAN STAR')
  assert.equal(findCandidate(investigation, '999'), null)

  const trajectories = { trajectories: [{ mmsi: '900000001' }] }
  assert.ok(findTrajectory(trajectories, '900000001'))
  assert.equal(findTrajectory(trajectories, 'other'), null)
  assert.equal(findTrajectory(null, '900000001'), null)
})

test('summariseList handles empty, single and many items', () => {
  assert.equal(summariseList([], 'none'), 'none')
  assert.equal(summariseList(['a']), 'a')
  assert.equal(summariseList(['a', 'b', 'c']), 'a; b; and c')
})
