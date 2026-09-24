/** Evidence factors in the order analysts read them, with plain-English labels. */
export const FACTOR_META = [
  { key: 'spatial', label: 'Spatial proximity', hint: 'Distance to the estimated origin region during the release window' },
  { key: 'temporal', label: 'Release-window presence', hint: 'Present inside the origin region while the window was open' },
  { key: 'trajectory', label: 'Trajectory plausibility', hint: 'Course changes and speeds that could physically carry the vessel into the region' },
  { key: 'behaviour', label: 'Behaviour anomaly', hint: 'Stop/slow/erratic behaviour versus the vessel own baseline' },
  { key: 'gap', label: 'AIS gap evidence', hint: 'A broadcast gap that overlaps the window and is physically feasible' },
]

export const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

/** `null`/`undefined`/NaN all render as an em dash rather than "NaN"/"null". */
export function fmtNumber(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function fmtInt(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Math.round(Number(value)).toLocaleString('en-US')
}

export function fmtKm(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return `${fmtNumber(value, digits)} km`
}

export function fmtPercent(fraction, digits = 0) {
  if (fraction === null || fraction === undefined || Number.isNaN(Number(fraction))) return '—'
  return `${fmtNumber(Number(fraction) * 100, digits)}%`
}

/** ISO-8601 UTC -> "14 Mar 2026 06:00 UTC". Times are always shown in UTC. */
export function fmtDateTime(iso) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return String(iso)
  const day = date.toUTCString().slice(5, 16) // "14 Mar 2026"
  const time = date.toISOString().slice(11, 16) // "06:00"
  return `${day} ${time} UTC`
}

/** Seconds -> "4h 00m" / "35m 12s" / "12s". */
export function fmtDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return '—'
  const total = Math.max(0, Math.round(Number(seconds)))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`
  if (m > 0) return `${m}m ${String(s).padStart(2, '0')}s`
  return `${s}s`
}

/** 0-1 confidence -> percent string; `fmtPercent` already does this. */
export const fmtConfidence = (value) => fmtPercent(value, 0)

/**
 * Flatten an entry's `factors` object into render-ready rows.
 * Points/maxPoints come straight from the API; a factor may be absent when the
 * pipeline did not score it, which is shown honestly as 0 of its cap.
 */
export function factorRows(factors) {
  const src = factors && typeof factors === 'object' ? factors : {}
  return FACTOR_META.map(({ key, label, hint }) => {
    const present = Object.prototype.hasOwnProperty.call(src, key)
    const factor = present && src[key] && typeof src[key] === 'object' ? src[key] : {}
    const points = Number(factor.points ?? 0)
    const maxPoints = Number(factor.maxPoints ?? 0)
    return {
      key,
      label,
      hint,
      available: present && Object.keys(factor).length > 0,
      points,
      maxPoints,
      percent: maxPoints > 0 ? clamp(points / maxPoints, 0, 1) : 0,
      detail: factor.detail ?? null,
    }
  })
}

/** Coarse label for a 0-100 score. Deliberately not phrased as a probability. */
export function scoreBand(score) {
  if (score === null || score === undefined || !Number.isFinite(Number(score))) {
    return { label: 'unscored', tone: 'neutral' }
  }
  const value = Number(score)
  if (value >= 70) return { label: 'strong evidence', tone: 'high' }
  if (value >= 40) return { label: 'moderate evidence', tone: 'moderate' }
  if (value > 0) return { label: 'weak evidence', tone: 'low' }
  return { label: 'no scoring evidence', tone: 'neutral' }
}

/** Pull the investigation's ranking entries, tolerating an unexpected shape. */
export function rankingEntries(investigation) {
  const entries = investigation?.ranking?.entries
  return Array.isArray(entries) ? entries : []
}

/** Find one vessel's entry by MMSI (string-safe, MMSIs are strings in the API). */
export function findCandidate(investigation, mmsi) {
  if (!mmsi) return null
  return rankingEntries(investigation).find((entry) => String(entry.mmsi) === String(mmsi)) || null
}

/** Look up a reconstructed trajectory by MMSI in the /ais/trajectory bundle. */
export function findTrajectory(trajectories, mmsi) {
  if (!trajectories || !Array.isArray(trajectories.trajectories) || !mmsi) return null
  return trajectories.trajectories.find((trajectory) => String(trajectory.mmsi) === String(mmsi)) || null
}

/** Aggregate an array of {value, label} into one sentence (used for warnings). */
export function summariseList(items, empty = 'None reported.') {
  const list = Array.isArray(items) ? items.filter(Boolean) : []
  if (list.length === 0) return empty
  if (list.length === 1) return list[0]
  return `${list.slice(0, -1).join('; ')}; and ${list[list.length - 1]}`
}

