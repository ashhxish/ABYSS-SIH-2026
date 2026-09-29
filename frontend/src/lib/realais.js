/**
 * Presentation helpers for the REAL AIS section of the real Sentinel-1 view
 * (Phase 21.5).
 *
 * Every function here is pure and reads ONLY from the `POST /ais/real/analyze`
 * payload plus the Sentinel-1 response's own scene bounds. Nothing invents a
 * vessel, a position, a timestamp or a score: a missing value stays `null` and
 * the UI is expected to say so. This module deliberately knows nothing about the
 * synthetic demo case, candidate scoring or attribution - the real view must
 * never display those.
 */

/** Shown verbatim wherever the temporal limitation is surfaced. */
export const TEMPORAL_LIMITATION_TEXT =
  'The Sentinel-1 acquisition timestamp is unavailable. The AIS observation shown here is a real NOAA AIS spatial match only and must not be interpreted as temporal attribution.'


const asArray = (value) => (Array.isArray(value) ? value : [])

/** West/south/east/north extent of the real Sentinel-1 scene, or null. */
export function sceneBoundsOf(s1Data) {
  const bounds =
    s1Data?.observation?.characteristics?.sceneBounds ?? s1Data?.result?.bounds
  if (!Array.isArray(bounds) || bounds.length !== 4) return null
  const nums = bounds.map(Number)
  return nums.every(Number.isFinite) ? nums : null
}

/** The payload's own counts, passed through unchanged (null when absent). */
export function realAisCounts(data) {
  const num = (value) => (Number.isFinite(Number(value)) ? Number(value) : null)
  return {
    raw: num(data?.rawRecordCount),
    accepted: num(data?.acceptedRecordCount),
    rejected: num(data?.rejectedRecordCount),
    warnings: num(data?.warningCount),
    vesselsLoaded: num(data?.uniqueMmsiCount),
    trajectories: num(data?.trajectoryCount),
    gaps: num(data?.gapCount),
    matchedVessels: num(data?.vesselCount),
    matchedPositions: num(data?.spatialMatchCount),
  }
}

/**
 * Positions the API actually returned inside the selection box, in payload
 * order and de-duplicated.
 *
 * The API reports the matched set as a start/end pair per vessel, so a vessel
 * with `matchedPointCount >= 2` contributes both endpoints; a single matched
 * report contributes one point. No interpolated or neighbouring point is ever
 * added, which is why a lone match is drawn as one marker and never as a track.
 */
export function matchedPositions(data) {
  const out = []
  const push = (vessel, point) => {
    // Reject null/undefined/''/non-numeric BEFORE coercion: Number(null) and
    // Number('') are both 0, which would silently plot a vessel at Null Island
    // (0,0) - a fabricated position. Anything not a real number is dropped.
    const rawLat = point?.latitude
    const rawLon = point?.longitude
    if (rawLat === null || rawLat === undefined || rawLat === '') return
    if (rawLon === null || rawLon === undefined || rawLon === '') return
    const lat = Number(rawLat)
    const lon = Number(rawLon)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return
    if (out.some((p) => p.lat === lat && p.lon === lon)) return
    out.push({ mmsi: vessel?.mmsi ?? null, vesselName: vessel?.vesselName ?? null, lat, lon })
  }
  for (const vessel of asArray(data?.vessels)) {
    if (Number(vessel?.matchedPointCount) >= 2) {
      push(vessel, vessel?.matchedFirstPosition)
      push(vessel, vessel?.matchedLastPosition)
    } else {
      push(vessel, vessel?.matchedFirstPosition ?? vessel?.matchedLastPosition)
    }
  }
  return out
}

/** The matched set is plottable as a track only when 2+ real points came back. */
export function hasMatchedTrack(data) {
  return matchedPositions(data).length >= 2
}

/**
 * Cross-check that the AIS selection box is the displayed SAR scene extent.
 * Returns null when either box is unavailable, so the UI can say "not verified"
 * instead of assuming a match.
 */
export function aisBoxMatchesScene(data, s1Data) {
  const box = data?.spatialBBox
  const scene = sceneBoundsOf(s1Data)
  if (!Array.isArray(box) || box.length !== 4 || !scene) return null
  return box.every((value, index) => Math.abs(Number(value) - scene[index]) < 1e-6)
}

/** Vessel rows for the matched-vessel card, verbatim from the payload. */
export function matchedVessels(data) {
  return asArray(data?.vessels).map((vessel) => ({
    mmsi: vessel?.mmsi ?? null,
    vesselName: vessel?.vesselName ?? null,
    imo: vessel?.imo ?? null,
    vesselType: vessel?.vesselType ?? null,
    matchedPointCount: Number.isFinite(Number(vessel?.matchedPointCount))
      ? Number(vessel.matchedPointCount)
      : null,
    matchedStartTimestamp: vessel?.matchedStartTimestamp ?? null,
    matchedEndTimestamp: vessel?.matchedEndTimestamp ?? null,
    matchedFirstPosition: vessel?.matchedFirstPosition ?? null,
    matchedLastPosition: vessel?.matchedLastPosition ?? null,
    pointCount: Number.isFinite(Number(vessel?.pointCount)) ? Number(vessel.pointCount) : null,
    gapCount: Number.isFinite(Number(vessel?.gapCount)) ? Number(vessel.gapCount) : null,
    startTimestamp: vessel?.startTimestamp ?? null,
    endTimestamp: vessel?.endTimestamp ?? null,
    firstPosition: vessel?.firstPosition ?? null,
    lastPosition: vessel?.lastPosition ?? null,
  }))
}

/** Number of distinct MMSI in the payload, used only as a consistency display. */
export function uniqueMatchedMmsi(data) {
  return new Set(matchedVessels(data).map((v) => String(v.mmsi))).size
}
