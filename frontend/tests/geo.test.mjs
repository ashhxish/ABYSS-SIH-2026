import assert from 'node:assert/strict'
import test from 'node:test'
import {
  boundsOf,
  graticule,
  haversineKm,
  lineToPath,
  makeProjector,
  niceScaleKm,
  normalisePoints,
  pointsToPath,
  ringToLatLon,
  ringToPath,
} from '../src/lib/geo.js'

test('normalisePoints accepts [lat,lon] pairs and {lat,lon} objects', () => {
  assert.deepEqual(normalisePoints([[18.5, 72.1], { lat: 18.6, lon: 72.2 }]), [
    { lat: 18.5, lon: 72.1 },
    { lat: 18.6, lon: 72.2 },
  ])
  assert.deepEqual(normalisePoints(['nope', [null, 1], {}]), [])
  assert.deepEqual(normalisePoints(undefined), [])
})

test('boundsOf pads the box and survives a single point', () => {
  const box = boundsOf([[18, 72]], 0)
  // zero-area boxes are widened symmetrically so the projection stays finite
  assert.ok(box.maxLat - box.minLat >= 0.02, `span ${box.maxLat - box.minLat}`)
  assert.ok(box.maxLon - box.minLon >= 0.02)
  assert.equal(box.minLat + (box.maxLat - box.minLat) / 2, 18)

  const padded = boundsOf([[18, 72], [19, 73]], 0.1)
  assert.equal(padded.minLat, 17.9)
  assert.equal(padded.maxLat, 19.1)
  assert.equal(padded.minLon, 71.9)
  assert.equal(boundsOf([], 0.1), null)
})

test('projector flips latitude (north is up) and keeps points in view', () => {
  const bounds = { minLat: 10, maxLat: 20, minLon: 70, maxLon: 74 }
  const p = makeProjector(bounds, 800, 400, 20)
  const [northX, northY] = p.project(20, 70)
  const [southX, southY] = p.project(10, 70)
  assert.equal(northX, southX)
  assert.ok(northY < southY, 'higher latitude must draw higher on screen')
  for (const [lat, lon] of [[10, 70], [15, 72], [20, 74]]) {
    const [x, y] = p.project(lat, lon)
    assert.ok(x >= 0 && x <= 800, `x in view for ${lat},${lon}`)
    assert.ok(y >= 0 && y <= 400, `y in view for ${lat},${lon}`)
  }
})

test('projector rejects missing bounds', () => {
  assert.equal(makeProjector(null, 100, 100), null)
})

test('path builders produce SVG data, with GeoJSON lon/lat order', () => {
  const p = makeProjector({ minLat: 18, maxLat: 19, minLon: 71, maxLon: 72 }, 400, 400, 10)
  const ring = ringToPath([[71, 18], [72, 18], [72, 19], [71, 18]], p)
  assert.match(ring, /^M [\d.]+ [\d.]+ L /)
  assert.ok(ring.endsWith('Z'), 'polygon path must close')

  const line = lineToPath([[71, 18], [72, 19]], p)
  assert.ok(line.startsWith('M ') && !line.endsWith('Z'))

  const pts = pointsToPath([[18, 71], [19, 72]], p)
  assert.ok(pts.startsWith('M '))

  assert.equal(ringToPath([[71, 18]], p), '')
  assert.equal(lineToPath([[71, 18]], p), '')
  assert.equal(pointsToPath([[18, 71]], p), '')
  assert.equal(pointsToPath([[18, 71], [19, 72]], null), '')
})

test('ringToLatLon swaps GeoJSON [lon,lat] into the [lat,lon] convention', () => {
  // A real CASE-001 vertex: lon 72.163105, lat 18.466325.
  assert.deepEqual(ringToLatLon([[72.163105, 18.466325]]), [{ lat: 18.466325, lon: 72.163105 }])
  assert.deepEqual(ringToLatLon(null), [])
  assert.deepEqual(ringToLatLon([null, ['x']]), [])

  // The regression this guards: measuring a raw GeoJSON ring with the [lat,lon]
  // normaliser swaps the axes, so bounds land in the wrong hemisphere and every
  // projected coordinate falls far outside the viewBox (an empty map).
  const slick = [[72.1165, 18.4297], [72.2097, 18.5029]]
  const region = [[71.7873, 18.2286], [72.0113, 18.2778], [71.96, 18.3778], [71.7873, 18.2286]]
  const correct = boundsOf([...ringToLatLon(slick), ...ringToLatLon(region)], 0.25)
  const wrong = boundsOf([...normalisePoints(slick), ...normalisePoints(region)], 0.25)

  assert.ok(correct.minLat > 18 && correct.maxLat < 19, 'latitudes stay in the demo area')
  assert.ok(correct.minLon > 71 && correct.maxLon < 73, 'longitudes stay in the demo area')
  // the swapped version reports latitude ~72 and longitude ~18
  assert.ok(wrong.minLat > 70 && wrong.maxLon < 20, 'swapped axes are visibly wrong')

  // and the projected geometry must land inside the viewport
  const p = makeProjector(correct, 860, 520, 46)
  const path = ringToPath(region, p)
  const coords = [...path.matchAll(/(-?\d+\.\d) (-?\d+\.\d)/g)].map((m) => [Number(m[1]), Number(m[2])])
  assert.ok(coords.length >= 3)
  for (const [x, y] of coords) {
    assert.ok(x >= -1 && x <= 861, `x ${x} inside viewport`)
    assert.ok(y >= -1 && y <= 521, `y ${y} inside viewport`)
  }
})

test('haversineKm matches a known distance and is symmetric', () => {
  const d = haversineKm(0, 0, 0, 1)
  assert.ok(Math.abs(d - 111.195) < 0.01, `got ${d}`)
  assert.ok(Math.abs(haversineKm(18.4, 72.1, 18.4, 72.1)) < 1e-9)
})

test('niceScaleKm returns a 1/2/5 x 10^n value that covers the target', () => {
  for (const kmPerPixel of [0.0005, 0.01, 0.3, 2, 50]) {
    const km = niceScaleKm(kmPerPixel, 90)
    assert.ok(km >= kmPerPixel * 90, `${km} should cover ${kmPerPixel * 90}`)
    const mantissa = km / 10 ** Math.floor(Math.log10(km))
    assert.ok([1, 2, 5].some((m) => Math.abs(mantissa - m) < 1e-9), `mantissa ${mantissa}`)
  }
})

test('graticule yields ticks inside the bounds', () => {
  const ticks = graticule({ minLat: 18.1, maxLat: 18.6, minLon: 71.7, maxLon: 72.3 }, 4)
  assert.ok(ticks.lats.length >= 1)
  assert.ok(ticks.lons.length >= 1)
  for (const lat of ticks.lats) assert.ok(lat >= 18.1 && lat <= 18.6)
  for (const lon of ticks.lons) assert.ok(lon >= 71.7 && lon <= 72.3)
  assert.deepEqual(graticule(null), { lats: [], lons: [] })
})
