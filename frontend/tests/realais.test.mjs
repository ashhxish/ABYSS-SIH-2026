import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { geoToFraction, makeProjector } from '../src/lib/geo.js'
import { fmtHemisphere, fmtLatLon, fmtLatitude, fmtLongitude, fmtUtcSeconds } from '../src/lib/format.js'
import {
  aisBoxMatchesScene,
  hasMatchedTrack,
  matchedPositions,
  matchedVessels,
  realAisCounts,
  sceneBoundsOf,
  TEMPORAL_LIMITATION_TEXT,
  uniqueMatchedMmsi,
} from '../src/lib/realais.js'

/**
 * Verified real values (Phase 21). They are hard-coded on purpose: these tests
 * pin the numbers the real service actually returned, so a presentation-layer
 * regression that silently changes what is displayed fails loudly.
 */
const SCENE_BOUNDS = [-93.53543528531954, 22.35006117228921, -93.35146031513186, 22.534036142476886]

const REAL_PAYLOAD = {
  label: 'REAL AIS INTEGRATION - TEMPORAL MATCH PENDING',
  realAis: true,
  source: { provider: 'NOAA/OAR/PMEL AIS', synthetic: false, uri: '/home/ashish/SIH/real_ais/ais_sample.csv' },
  temporalMatchAvailable: false,
  temporalMatchReason: 'Sentinel-1 acquisition timestamp unavailable.',
  rawRecordCount: 3039,
  acceptedRecordCount: 3034,
  rejectedRecordCount: 5,
  warningCount: 656,
  uniqueMmsiCount: 815,
  filteredRecordCount: 1,
  vesselCount: 1,
  trajectoryCount: 815,
  gapCount: 2213,
  spatialFilterApplied: true,
  spatialBBox: SCENE_BOUNDS,
  spatialMatchCount: 1,
  vessels: [
    {
      mmsi: '309987000',
      vesselName: 'LILLESAND',
      imo: 'IMO9336397',
      vesselType: 80,
      matchedPointCount: 1,
      matchedStartTimestamp: '2024-05-29T01:15:52Z',
      matchedEndTimestamp: '2024-05-29T01:15:52Z',
      matchedFirstPosition: { latitude: 22.51457, longitude: -93.50463 },
      matchedLastPosition: { latitude: 22.51457, longitude: -93.50463 },
      pointCount: 8,
      gapCount: 0,
      startTimestamp: '2024-05-20T11:15:49Z',
      endTimestamp: '2024-05-31T14:16:22Z',
      firstPosition: { latitude: 21.88798, longitude: -91.01566 },
      lastPosition: { latitude: 23.50209, longitude: -91.73743 },
    },
  ],
}

const S1_DATA = { observation: { characteristics: { sceneBounds: SCENE_BOUNDS } }, result: { bounds: SCENE_BOUNDS } }

/* ------------------------------------------------------------------ payload */

test('realAisCounts reproduces the verified Phase-21 counts exactly', () => {
  const counts = realAisCounts(REAL_PAYLOAD)
  assert.equal(counts.raw, 3039)
  assert.equal(counts.accepted, 3034)
  assert.equal(counts.rejected, 5)
  assert.equal(counts.warnings, 656)
  assert.equal(counts.vesselsLoaded, 815)
  assert.equal(counts.trajectories, 815)
  assert.equal(counts.gaps, 2213)
  assert.equal(counts.matchedVessels, 1)
  assert.equal(counts.matchedPositions, 1)
})

test('realAisCounts keeps dataset size and spatial match as separate numbers', () => {
  const counts = realAisCounts(REAL_PAYLOAD)
  // Guards the exact confusion the UI must not make: 815 vessels are LOADED,
  // only 1 of them is SPATIALLY MATCHED. These are never conflated.
  assert.notEqual(counts.vesselsLoaded, counts.matchedVessels)
  assert.equal(counts.vesselsLoaded, 815)
  assert.equal(counts.matchedVessels, 1)
})

test('realAisCounts returns null for absent values instead of inventing zero', () => {
  const counts = realAisCounts({})
  for (const key of Object.keys(counts)) assert.equal(counts[key], null, key)
  assert.equal(realAisCounts(undefined).raw, null)
})

/* --------------------------------------------------------------- selection */

test('matchedPositions returns only the one real matched report', () => {
  const points = matchedPositions(REAL_PAYLOAD)
  assert.equal(points.length, 1)
  assert.deepEqual(points[0], { mmsi: '309987000', vesselName: 'LILLESAND', lat: 22.51457, lon: -93.50463 })
})

test('a single matched report is NOT a track (no invented polyline)', () => {
  // 8 reports exist in the extract-wide trajectory, but only 1 is inside the
  // scene box. The UI must therefore draw one marker, never an 8-point track.
  assert.equal(hasMatchedTrack(REAL_PAYLOAD), false)
  assert.equal(matchedPositions(REAL_PAYLOAD).length < 2, true)
})

test('hasMatchedTrack is true only when the API returned two distinct real points', () => {
  const two = {
    vessels: [
      {
        mmsi: '1',
        matchedPointCount: 2,
        matchedFirstPosition: { latitude: 10, longitude: 20 },
        matchedLastPosition: { latitude: 11, longitude: 21 },
      },
    ],
  }
  assert.equal(hasMatchedTrack(two), true)
  assert.equal(matchedPositions(two).length, 2)
  // The same point twice is one location, not a track.
  const same = {
    vessels: [
      {
        mmsi: '1',
        matchedPointCount: 2,
        matchedFirstPosition: { latitude: 10, longitude: 20 },
        matchedLastPosition: { latitude: 10, longitude: 20 },
      },
    ],
  }
  assert.equal(matchedPositions(same).length, 1)
  assert.equal(hasMatchedTrack(same), false)
})

test('matchedPositions never fabricates a position from missing fields', () => {
  const bad = {
    vessels: [
      { mmsi: '1', matchedPointCount: 1, matchedFirstPosition: { latitude: null, longitude: null } },
      { mmsi: '2', matchedPointCount: 1 },
      { mmsi: '3', matchedPointCount: 1, matchedFirstPosition: { latitude: 5, longitude: 'x' } },
    ],
  }
  assert.deepEqual(matchedPositions(bad), [])
  assert.equal(hasMatchedTrack(bad), false)
  assert.deepEqual(matchedPositions({ vessels: null }), [])
  assert.deepEqual(matchedPositions(undefined), [])
})

/* ------------------------------------------------------------ matched rows */

test('matchedVessels returns the verified LILLESAND row verbatim', () => {
  const [vessel] = matchedVessels(REAL_PAYLOAD)
  assert.equal(vessel.mmsi, '309987000')
  assert.equal(vessel.vesselName, 'LILLESAND')
  assert.equal(vessel.imo, 'IMO9336397')
  assert.equal(vessel.vesselType, 80)
  assert.equal(vessel.matchedPointCount, 1)
  assert.equal(vessel.matchedStartTimestamp, '2024-05-29T01:15:52Z')
  assert.equal(vessel.matchedFirstPosition.latitude, 22.51457)
  assert.equal(vessel.matchedFirstPosition.longitude, -93.50463)
  // extract-wide trajectory context is carried through, not recomputed
  assert.equal(vessel.pointCount, 8)
  assert.equal(vessel.firstPosition.latitude, 21.88798)
  assert.equal(vessel.lastPosition.longitude, -91.73743)
})

test('matchedVessels normalises absent fields to null (no invented values)', () => {
  const [vessel] = matchedVessels({ vessels: [{ mmsi: '1' }] })
  assert.equal(vessel.vesselName, null)
  assert.equal(vessel.imo, null)
  assert.equal(vessel.vesselType, null)
  assert.equal(vessel.matchedPointCount, null)
  assert.equal(vessel.matchedStartTimestamp, null)
  assert.deepEqual(matchedVessels({}), [])
  assert.deepEqual(matchedVessels(undefined), [])
})

test('uniqueMatchedMmsi counts distinct matched vessels, not loaded vessels', () => {
  assert.equal(uniqueMatchedMmsi(REAL_PAYLOAD), 1)
  assert.notEqual(uniqueMatchedMmsi(REAL_PAYLOAD), realAisCounts(REAL_PAYLOAD).vesselsLoaded)
  assert.equal(uniqueMatchedMmsi({ vessels: [{ mmsi: 1 }, { mmsi: '1' }, { mmsi: 2 }] }), 2)
})

/* ------------------------------------------------- coordinate overlay maths */

test('geoToFraction places the real matched position inside the SAR scene', () => {
  const point = geoToFraction(22.51457, -93.50463, SCENE_BOUNDS)
  assert.ok(point, 'expected a projected point')
  assert.equal(point.inside, true)
  // north-west quadrant of the scene, matching the real geometry
  assert.ok(point.x > 0 && point.x < 0.5, `x=${point.x}`)
  assert.ok(point.y > 0 && point.y < 0.5, `y=${point.y}`)
  // scene corners map to the exact corners of the viewport
  const nw = geoToFraction(SCENE_BOUNDS[3], SCENE_BOUNDS[0], SCENE_BOUNDS)
  assert.ok(Math.abs(nw.x) < 1e-9 && Math.abs(nw.y) < 1e-9)
  const se = geoToFraction(SCENE_BOUNDS[1], SCENE_BOUNDS[2], SCENE_BOUNDS)
  assert.ok(Math.abs(se.x - 1) < 1e-9 && Math.abs(se.y - 1) < 1e-9)
})

test('geoToFraction flags out-of-scene positions instead of clamping them', () => {
  // LILLESAND's extract-wide endpoints lie far outside the Sentinel-1 footprint:
  // both longitudes are EAST of the scene (-91.x vs the scene's -93.5..-93.35)
  // and the last latitude is NORTH of it, so both map beyond the viewport.
  const first = geoToFraction(21.88798, -91.01566, SCENE_BOUNDS)
  const last = geoToFraction(23.50209, -91.73743, SCENE_BOUNDS)
  assert.equal(first.inside, false)
  assert.equal(last.inside, false)
  assert.ok(first.x > 1, 'longitude east of the scene')
  assert.ok(last.y < 0, 'latitude north of the scene')
  // out-of-scene is reported, never clamped to an edge
  assert.notEqual(first.x, 1)
  assert.notEqual(last.y, 0)
})

/* -------------------------------------------------------------- formatting */

test('fmtUtcSeconds shows the matched timestamp to the second in UTC', () => {
  assert.equal(fmtUtcSeconds('2024-05-29T01:15:52Z'), '2024-05-29 01:15:52 UTC')
  assert.equal(fmtUtcSeconds('2024-05-29T01:15:52.123456Z'), '2024-05-29 01:15:52 UTC')
  assert.equal(fmtUtcSeconds('2024-05-29 01:15:52'), '2024-05-29 01:15:52 UTC')
  // A missing acquisition time must render as an em dash, never as today's date.
  assert.equal(fmtUtcSeconds(null), '—')
  assert.equal(fmtUtcSeconds(undefined), '—')
  assert.equal(fmtUtcSeconds(''), '—')
})

test('latitude/longitude render with the correct hemisphere sign', () => {
  assert.equal(fmtLatitude(22.51457), '22.51457°N')
  assert.equal(fmtLongitude(-93.50463), '93.50463°W')
  assert.equal(fmtLatLon(22.51457, -93.50463), '22.51457°N, 93.50463°W')
  assert.equal(fmtLatitude(-22.51457), '22.51457°S')
  assert.equal(fmtLongitude(93.50463), '93.50463°E')
  assert.equal(fmtLatitude(null), '—')
  assert.equal(fmtLongitude(undefined), '—')
})

/* --------------------------------------------------- forensic / honesty guard */

test('the temporal limitation text forbids temporal attribution', () => {
  assert.match(TEMPORAL_LIMITATION_TEXT, /acquisition timestamp is unavailable/i)
  assert.match(TEMPORAL_LIMITATION_TEXT, /must not be interpreted as temporal attribution/i)
  assert.match(TEMPORAL_LIMITATION_TEXT, /real NOAA AIS spatial match only/i)
})


/* --------------------------------------------------- source-code integrity */

const read = (relative) =>
  readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8')

const SOURCE_FILES = [
  '../src/components/RealAisPanel.jsx',
  '../src/components/Sentinel1Panel.jsx',
  '../src/lib/realais.js',
]

test('the real view never imports the synthetic scoring modules', () => {
  for (const file of SOURCE_FILES) {
    const source = read(file)
    assert.equal(/from ['"]\.\.\/lib\/(evidence|report|timeline)\.js['"]/.test(source), false, file)
    assert.equal(/rankingEntries|totalScore|factorRows/.test(source), false, file)
  }
})

test('the real view never renders CASE-001 demo labels or candidates', () => {
  for (const file of SOURCE_FILES) {
    const source = read(file)
    assert.equal(source.includes('Synthetic Demonstration Dataset'), false, file)
    assert.equal(/V00[0-9]/.test(source), false, file)
    assert.equal(source.includes('CASE-001'), false, file)
  }
})

test('the real view never uses attribution or blame wording', () => {
  for (const file of SOURCE_FILES) {
    const source = read(file)
    for (const word of ['culprit', 'responsible for', 'responsible vessel']) {
      assert.equal(new RegExp(word, 'i').test(source), false, `${file} contains "${word}"`)
    }
  }
})

test('the required real-AIS facts are rendered by the panel', () => {
  const source = read('../src/components/RealAisPanel.jsx')
  assert.match(source, /REAL AIS TRAFFIC/)
  assert.match(source, /AIS records loaded/)
  assert.match(source, /Unique vessels loaded/)
  assert.match(source, /Spatially matched vessels/)
  assert.match(source, /Spatially matched positions/)
  assert.match(source, /TEMPORAL MATCH: UNAVAILABLE/)
  assert.match(source, /Matched reports/)
  assert.match(source, /0 spatially matched vessels/)
  assert.match(source, /REAL AIS SERVICE UNAVAILABLE/)
})

/* ------------------------------------------- hemisphere correctness (regression) */

/**
 * Regression guard: the CASE-001 scene sits near 22.4N, -93.4E (Gulf of
 * Campeche), i.e. a WESTERN longitude. Rendering a raw negative longitude with a
 * hardcoded "°E" suffix prints "-93.4044°E", which is both unsightly and
 * geographically wrong. Components must use the tested hemisphere helpers.
 */

/** Every JSX/JS source that renders coordinates. */
const COORD_SOURCE_FILES = [
  '../src/components/Header.jsx',
  '../src/components/ObservationCard.jsx',
  '../src/components/MapPanel.jsx',
  '../src/components/UnifiedMapPanel.jsx',
]

test('no component hardcodes a hemisphere suffix onto a raw coordinate', () => {
  for (const file of COORD_SOURCE_FILES) {
    const source = read(file)
    // e.g. `${lon, 4)}°E` or `Math.abs(m.lon).toFixed(2)}°W`
    assert.equal(/\}\s*°[NSEW]/.test(source), false, `${file} appends a raw hemisphere suffix`)
  }
})

test('coordinate renderers use the tested hemisphere helpers', () => {
  for (const file of COORD_SOURCE_FILES) {
    const source = read(file)
    assert.match(source, /fmtLatLon|fmtLatitude|fmtLongitude/, `${file} uses no hemisphere helper`)
  }
})

test('the real scene centroid renders as a western longitude', () => {
  // Phase 1 verified centroid: 22.46282, -93.44692
  assert.equal(fmtLatLon(22.46282, -93.44692, 5), '22.46282°N, 93.44692°W')
  // The old broken form that this suite now prevents.
  assert.notEqual(`${(-93.44692).toFixed(5)}°E`, '93.44692°W')
})

test('the demo slick centroid renders as a western longitude', () => {
  assert.equal(fmtLatLon(22.41, -93.4, 4), '22.4100°N, 93.4000°W')
})

/* --------------------------------------- responsibility-language sweep (UI-wide) */

/**
 * These phrases are forbidden anywhere in rendered UI source. Negated forms
 * ("not a probability of responsibility") are allowed; the guard therefore
 * checks for affirmative use only, and the explicit list below documents the
 * exact wording that must never ship.
 */
const RESPONSIBILITY_SCAN_FILES = [
  ...COORD_SOURCE_FILES,
  '../src/components/CandidateTable.jsx',
  '../src/components/CandidateDetail.jsx',
  '../src/components/EvidenceChain.jsx',
  '../src/components/InvestigatorReviewPanel.jsx',
  '../src/components/EvidenceFusionPanel.jsx',
  '../src/components/InvestigationHome.jsx',
  '../src/components/ConfidencePanel.jsx',
]

test('no UI component uses affirmative responsibility or blame wording', () => {
  const banned = [
    /\bguilty\b/i,
    /\bculprit\b/i,
    /confirmed responsible/i,
    /responsible vessel/i,
    /probability of guilt/i,
  ]
  for (const file of RESPONSIBILITY_SCAN_FILES) {
    const source = read(file)
    for (const pattern of banned) {
      assert.equal(pattern.test(source), false, `${file} matches ${pattern}`)
    }
  }
})

test('the score disclaimer states it is not a probability of responsibility', () => {
  const source = read('../src/components/CandidateTable.jsx')
  assert.match(source, /not a probability of responsibility/i)
})


test('the AIS overlay is drawn from real positions only, with no synthetic fallback', () => {
  const source = read('../src/components/Sentinel1Panel.jsx')
  assert.match(source, /matchedPositions/)
  assert.match(source, /sceneBoundsOf/)
  // A failure must surface, never silently fall back to synthetic AIS.
  assert.equal(/fetchInvestigation|investigation\.data|fetchTrajectories/.test(source), false)
})

test('the real-AIS payload never carries a responsibility score or ranking', () => {
  const text = JSON.stringify(REAL_PAYLOAD)
  for (const forbidden of ['totalScore', 'ranking', 'candidates', 'responsibility', 'culprit']) {
    assert.equal(text.includes(forbidden), false, `real payload must not contain ${forbidden}`)
  }
  assert.equal(REAL_PAYLOAD.temporalMatchAvailable, false)
  assert.equal(REAL_PAYLOAD.realAis, true)
  assert.equal(REAL_PAYLOAD.source.synthetic, false)
})

test('geoToFraction returns null rather than dividing by a degenerate box', () => {
  assert.equal(geoToFraction(1, 1, null), null)
  assert.equal(geoToFraction(1, 1, [1, 2, 3]), null)
  assert.equal(geoToFraction(1, 1, [5, 5, 5, 5]), null) // zero span
  assert.equal(geoToFraction(null, null, SCENE_BOUNDS), null)
  assert.equal(geoToFraction(10, 20, ['a', 'b', 'c', 'd']), null)
})


test('matchedPositions de-duplicates identical positions', () => {
  const dup = {
    vessels: [
      { mmsi: '1', matchedPointCount: 1, matchedFirstPosition: { latitude: 10, longitude: 20 } },
      { mmsi: '2', matchedPointCount: 1, matchedFirstPosition: { latitude: 10, longitude: 20 } },
    ],
  }
  assert.equal(matchedPositions(dup).length, 1)
})

test('realAisCounts passes real zero through as zero (honest empty selection)', () => {
  const empty = realAisCounts({ spatialMatchCount: 0, vesselCount: 0 })
  assert.equal(empty.matchedPositions, 0)
  assert.equal(empty.matchedVessels, 0)
})

/* ------------------------------------------------------------- scene bounds */

test('sceneBoundsOf reads the real scene extent from the Sentinel-1 response', () => {
  assert.deepEqual(sceneBoundsOf(S1_DATA), SCENE_BOUNDS)
  assert.equal(sceneBoundsOf({ result: { bounds: SCENE_BOUNDS } })[0], SCENE_BOUNDS[0])
  assert.equal(sceneBoundsOf({}), null)
  assert.equal(sceneBoundsOf({ observation: { characteristics: { sceneBounds: [1, 2] } } }), null)
  assert.equal(sceneBoundsOf({ observation: { characteristics: { sceneBounds: ['a', 2, 3, 4] } } }), null)
})

test('the AIS selection box is the real Sentinel-1 scene box', () => {
  assert.equal(aisBoxMatchesScene(REAL_PAYLOAD, S1_DATA), true)
  assert.equal(aisBoxMatchesScene(REAL_PAYLOAD, { result: { bounds: [-96, 21.5, -93, 24.5] } }), false)
  // Unknown on either side -> "not verified", never an assumed match.
  assert.equal(aisBoxMatchesScene(REAL_PAYLOAD, {}), null)
  assert.equal(aisBoxMatchesScene({}, S1_DATA), null)
})


/* ------------------------------------------------- runtime configuration */

/**
 * The scene path is server-side configuration, not a UI constant. These guard
 * the two failure modes that are silent at runtime: a variable name that drifts
 * between the code and the documented env template, and a build with no scene
 * configured that posts a blank `scenePath` into a required field.
 */

test('the API base URL variable is the same one the env template documents', () => {
  const api = read('../src/api.js')
  const template = read('../../.env.example')
  // .env.example previously advertised VITE_ABYSS_API_BASE_URL, which no code
  // read - following the docs silently fell back to the '/api' default.
  assert.match(api, /import\.meta\.env\.VITE_API_BASE_URL/)
  assert.equal(template.includes('VITE_ABYSS_API_BASE_URL'), false)
  assert.match(template, /VITE_API_BASE_URL/)
})

test('the scene path is configured by env, never hardcoded in a component', () => {
  const api = read('../src/api.js')
  const app = read('../src/App.jsx')
  assert.match(api, /import\.meta\.env\.VITE_SENTINEL1_SCENE_PATH/)
  // A developer's home directory must not be baked into the shipped source.
  assert.equal(/\/home\/[a-z0-9_.-]+\//.test(app), false, 'App.jsx hardcodes an absolute local path')
  assert.match(app, /scenePath: SENTINEL1_SCENE_PATH/)
})

test('an unconfigured scene is reported, never posted as a blank required field', () => {
  const app = read('../src/App.jsx')
  const guardIndex = app.indexOf('isSentinel1Configured()')
  const callIndex = app.indexOf('fetchSentinel1Detect(')
  assert.ok(guardIndex > -1, 'loadSentinel1 must check isSentinel1Configured()')
  assert.ok(callIndex > -1, 'loadSentinel1 must still call the service')
  assert.ok(guardIndex < callIndex, 'the guard must run before the request')
  assert.match(app, /VITE_SENTINEL1_SCENE_PATH/)
})


/* -------------------------------------- projection return-type crash regression */

const MAP_SOURCE_FILES = [
  '../src/components/MapPanel.jsx',
  '../src/components/UnifiedMapPanel.jsx',
  '../src/components/Sentinel1Panel.jsx',
]

/**
 * `makeProjector(...).project(lat, lon)` returns an [x, y] ARRAY, not an
 * {x, y} object.
 *
 * `UnifiedMapPanel` used to carry private copies of the path builders that read
 * `point.x` / `point.y`. On an array both are `undefined`, so
 * `undefined.toFixed(1)` threw during render. `App.jsx` has no error boundary,
 * so React unmounted the entire tree and left `#root` empty - clicking START
 * INVESTIGATION produced a completely blank page. These guards fail if that
 * array/object mismatch is ever reintroduced.
 */
test('the projector contract is an [x, y] array, not an {x, y} object', () => {
  const projector = makeProjector({ minLat: 18, maxLat: 19, minLon: 71, maxLon: 72 }, 400, 400, 10)
  const point = projector.project(18.5, 71.5)
  assert.ok(Array.isArray(point), 'project() must return an array')
  assert.equal(point.length, 2)
  assert.ok(Number.isFinite(point[0]) && Number.isFinite(point[1]))
  // The object-style reads that used to crash really are undefined.
  assert.equal(point.x, undefined)
  assert.equal(point.y, undefined)
})

test('no component reads .x/.y off a projector result', () => {
  const objectStyle = /project\s*\([^)]*\)\s*\??\.\s*[xy]\b/g
  for (const file of MAP_SOURCE_FILES) {
    const hits = read(file).match(objectStyle) || []
    assert.deepEqual(hits, [], `${file} reads .x/.y off project(): ${hits.join(', ')}`)
  }
})

test('maps reuse the tested path builders instead of redeclaring them', () => {
  for (const file of MAP_SOURCE_FILES) {
    const source = read(file)
    for (const helper of ['ringToPath', 'lineToPath', 'pointsToPath']) {
      assert.equal(
        new RegExp(`function\\s+${helper}\\s*\\(`).test(source),
        false,
        `${file} redeclares ${helper}() instead of importing it from lib/geo.js`,
      )
    }
  }
})

test('UnifiedMapPanel consumes the shapes lib/geo.js actually returns', () => {
  const source = read('../src/components/UnifiedMapPanel.jsx')
  // graticule() returns { lats, lons } of plain numbers; reading
  // ticks.parallels / ticks.meridians yields undefined and throws on .map().
  assert.equal(
    /ticks\.parallels|ticks\.meridians/.test(source),
    false,
    'graticule() has no parallels/meridians keys',
  )
  // boundsOf() returns minLat/maxLat/minLon/maxLon; there is no west/south.
  assert.equal(
    /bounds\.west|bounds\.south|bounds\.east|bounds\.north/.test(source),
    false,
    'boundsOf() returns minLat/maxLat/minLon/maxLon',
  )
})

test('the SAR slick area label is measured, never hardcoded', () => {
  const source = read('../src/components/UnifiedMapPanel.jsx')
  // The SAR slick area is measured, never a literal baked into the SVG text.
  assert.match(source, /s1Data\?\.result\?\.areaKm2/)
  assert.equal(
    /SAR Slick \(18\.73/.test(source),
    false,
    'the slick area label must come from the inference result',
  )
})

