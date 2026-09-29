/**
 * Small equirectangular map projection, implemented locally so the console needs
 * no tile server, map SDK, or API key. It is a *schematic* plot: straight lines
 * in lon/lat space with a cos(latitude) correction so east-west distances are not
 * stretched. Accurate enough for a demo plot, not for navigation - and the UI
 * labels it as an indicative plot.
 */

const toRad = (deg) => (Number(deg) * Math.PI) / 180
const toDeg = (rad) => (rad * 180) / Math.PI

const isFiniteNumber = (v) => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v))

/** Accepts [lat, lon] pairs or {lat, lon} objects; ignores anything unusable. */
export function normalisePoints(points) {
  if (!Array.isArray(points)) return []
  const out = []
  for (const p of points) {
    if (Array.isArray(p) && p.length >= 2) {
      if (isFiniteNumber(p[0]) && isFiniteNumber(p[1])) {
        out.push({ lat: Number(p[0]), lon: Number(p[1]) })
      }
    } else if (p && typeof p === 'object') {
      const lat = p.lat ?? p.latitude
      const lon = p.lon ?? p.longitude
      if (isFiniteNumber(lat) && isFiniteNumber(lon)) out.push({ lat: Number(lat), lon: Number(lon) })
    }
  }
  return out
}

/**
 * GeoJSON is [lon, lat] everywhere; `normalisePoints` is [lat, lon] (as used by
 * the API's backdrift path). Mixing the two silently projects points into the
 * wrong hemisphere, so every GeoJSON ring goes through this converter first.
 */
export function ringToLatLon(ring) {
  if (!Array.isArray(ring)) return []
  return normalisePoints(
    ring
      .filter((p) => Array.isArray(p) && p.length >= 2)
      .map((p) => [p[1], p[0]]),
  )
}

/** Bounding box of a point list, padded by `padRatio` so edges are not clipped. */
export function boundsOf(points, padRatio = 0.08) {
  const pts = normalisePoints(points)
  if (pts.length === 0) return null
  let minLat = Infinity
  let maxLat = -Infinity
  let minLon = Infinity
  let maxLon = -Infinity
  for (const { lat, lon } of pts) {
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
    if (lon < minLon) minLon = lon
    if (lon > maxLon) maxLon = lon
  }
  // A single point (or an exactly flat line) would give a zero-area box, which
  // makes the projection divide by zero - widen it symmetrically instead.
  const minSpan = 0.02
  const grow = (lo, hi, ratio) => {
    let a = lo - (hi - lo) * ratio
    let b = hi + (hi - lo) * ratio
    if (b - a < minSpan) {
      const mid = (a + b) / 2
      a = mid - minSpan / 2
      b = mid + minSpan / 2
    }
    return { min: a, max: b }
  }
  const lat = grow(minLat, maxLat, padRatio)
  const lon = grow(minLon, maxLon, padRatio)
  return {
    minLat: lat.min,
    maxLat: lat.max,
    minLon: lon.min,
    maxLon: lon.max,
  }
}

/**
 * Build a projector that fits `bounds` into width x height, preserving aspect
 * ratio and centring the result.
 */
export function makeProjector(bounds, width, height, padding = 28) {
  if (!bounds) return null
  const midLat = (bounds.minLat + bounds.maxLat) / 2
  const lonScale = Math.cos(toRad(midLat)) || 1

  const spanX = (bounds.maxLon - bounds.minLon) * lonScale
  const spanY = bounds.maxLat - bounds.minLat
  const usableW = Math.max(1, width - padding * 2)
  const usableH = Math.max(1, height - padding * 2)
  const scale = Math.min(usableW / spanX, usableH / spanY)

  const drawnW = spanX * scale
  const drawnH = spanY * scale
  const offsetX = padding + (usableW - drawnW) / 2
  const offsetY = padding + (usableH - drawnH) / 2

  const project = (lat, lon) => {
    const x = offsetX + (Number(lon) - bounds.minLon) * lonScale * scale
    // SVG y grows downward; latitude grows north, so flip.
    const y = offsetY + (bounds.maxLat - Number(lat)) * scale
    return [x, y]
  }

  return {
    project,
    bounds,
    scale,
    /** Approximate ground resolution, used for the scale bar. */
    kmPerPixel: 111.32 / scale,
    spanDegrees: { lat: spanY, lon: bounds.maxLon - bounds.minLon },
  }
}

/** GeoJSON ring ([[lon, lat], ...]) -> SVG path data for a closed polygon. */
export function ringToPath(ring, projector) {
  if (!projector || !Array.isArray(ring) || ring.length === 0) return ''
  const pts = ring
    .map((p) => (Array.isArray(p) ? projector.project(p[1], p[0]) : null))
    .filter(Boolean)
  if (pts.length < 3) return ''
  return `M ${pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(' L ')} Z`
}

/** GeoJSON LineString ([[lon, lat], ...]) -> SVG polyline path. */
export function lineToPath(coordinates, projector) {
  if (!projector || !Array.isArray(coordinates) || coordinates.length < 2) return ''
  const pts = coordinates
    .map((p) => (Array.isArray(p) ? projector.project(p[1], p[0]) : null))
    .filter(Boolean)
  if (pts.length < 2) return ''
  return `M ${pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(' L ')}`
}

/** [{lat, lon}] -> SVG polyline path (used for the backdrift path). */
export function pointsToPath(points, projector) {
  if (!projector || !Array.isArray(points) || points.length < 2) return ''
  const pts = normalisePoints(points).map(({ lat, lon }) => projector.project(lat, lon))
  if (pts.length < 2) return ''
  return `M ${pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(' L ')}`
}
/** Great-circle distance in km - used for the map scale bar. */
export function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371.0088
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)))
}

/** "Nice" scale-bar length in km (1, 2, 5 x 10^n) for a target pixel length. */
export function niceScaleKm(kmPerPixel, targetPixels = 90) {
  const raw = Math.max(1e-9, kmPerPixel * targetPixels)
  const pow = Math.floor(Math.log10(raw))
  const base = 10 ** pow
  const candidates = [1, 2, 5, 10].map((m) => m * base)
  return candidates.find((c) => c >= raw) ?? candidates[candidates.length - 1]
}

/** Latitude/longitude graticule ticks for the axis labels. */
export function graticule(bounds, maxTicks = 4) {
  if (!bounds) return { lats: [], lons: [] }
  const stepFor = (span) => {
    const raw = span / maxTicks
    const pow = Math.floor(Math.log10(raw))
    const base = 10 ** pow
    return [1, 2, 5, 10].map((m) => m * base).find((s) => s >= raw) ?? base * 10
  }
  const ticks = (min, max, stride) => {
    const out = []
    if (!(stride > 0)) return out
    for (let v = Math.ceil(min / stride) * stride; v <= max + 1e-9; v += stride) {
      out.push(Number(v.toFixed(6)))
    }
    return out
  }
  return {
    lats: ticks(bounds.minLat, bounds.maxLat, stepFor(bounds.maxLat - bounds.minLat)),
    lons: ticks(bounds.minLon, bounds.maxLon, stepFor(bounds.maxLon - bounds.minLon)),
  }
}

/**
 * Map a geographic position onto its fractional position inside a
 * `[west, south, east, north]` box: `x` and `y` are 0..1 with y growing
 * downward (screen order), plus an `inside` flag.
 *
 * Used to place the real AIS matched position on top of the real Sentinel-1
 * raster preview. The supplied scene (00999.tif) is an EPSG:4326 raster on an
 * axis-aligned grid, so its geographic `bounds` are exactly its extent and this
 * linear mapping reproduces the raster's own affine transform (verified against
 * rasterio: both give x=0.167443, y=0.105809 for the LILLESAND position).
 *
 * Returns `null` for a missing/degenerate box or an unusable position, so the
 * caller skips the marker rather than drawing it at a guessed location.
 */
export function geoToFraction(lat, lon, bounds) {
  if (!Array.isArray(bounds) || bounds.length !== 4) return null
  const [west, south, east, north] = bounds.map(Number)
  if (![west, south, east, north].every(Number.isFinite)) return null
  const spanLon = east - west
  const spanLat = north - south
  if (!(spanLon > 0) || !(spanLat > 0)) return null
  if (!isFiniteNumber(lat) || !isFiniteNumber(lon)) return null
  const x = (Number(lon) - west) / spanLon
  const y = (north - Number(lat)) / spanLat
  return { x, y, inside: x >= 0 && x <= 1 && y >= 0 && y <= 1 }
}

export { toDeg, toRad }


