/**
 * Phase 16 - forensic investigation timeline.
 *
 * Every value produced here is read from an existing API response (`/investigate`
 * and `/detect`). Nothing is invented: an event whose underlying API payload
 * carries no timestamp is returned with `at: null` and rendered as untimed
 * analysis context instead of being given a made-up time on the clock.
 */

/** Provenance labels, keyed to the API path each displayed value came from. */
export const SOURCE = Object.freeze({
  DETECTION: 'detection',
  CHARACTERISATION: 'detection.characterisation',
  LOOK_ALIKE: 'detection.lookAlikeAssessment',
  OBSERVED_AT: 'origin.observedAt',
  RELEASE_WINDOW: 'origin.releaseWindow',
  DRIFT: 'origin.drift',
  REGION: 'origin.region',
  COMPATIBILITY: 'ranking[].compatibility',
  BEHAVIOUR: 'ranking[].behaviour',
  GAPS: 'ranking[].gapAnalysis',
  FACTORS: 'ranking[].factors',
  STATISTICS: 'investigation.statistics',
  WEIGHTS: 'investigation.weights',
  RANKING: 'investigation.ranking',
})

/**
 * How each timeline entry relates to reality.
 *  OBSERVED    - directly recorded: a satellite acquisition, or AIS reports
 *                (including the observed *absence* of reports during a gap).
 *  PRIOR       - supplied with the case as an explicit input; not derived here.
 *  MODELLED    - output of the drift/hindcast and its derived geometry.
 *  ANALYTICAL  - a comparison or score computed from two or more evidence items.
 */
export const EVIDENCE_STATUS = Object.freeze({
  OBSERVED: 'OBSERVED',
  PRIOR: 'PRIOR',
  MODELLED: 'MODELLED',
  ANALYTICAL: 'ANALYTICAL',
})

/** Short explanations shown beside each status chip. */
export const STATUS_MEANING = Object.freeze({
  OBSERVED: 'recorded by an instrument',
  PRIOR: 'case-input prior, not derived from the slick',
  MODELLED: 'output of the drift model',
  ANALYTICAL: 'computed from other evidence',
})

/** Grouping used for the evidence-type chips in the UI. */
export const EVIDENCE_TYPE = Object.freeze({
  SATELLITE: 'Satellite',
  AIS: 'AIS',
  MODEL: 'Model',
  SCORING: 'Scoring',
})

/** Shown for analysis steps the API response carries no timestamp for. */
export const UNTIMED_NOTE =
  'No timestamp for this step exists in the API response, so it is not placed on the clock.'

/** Read a nested value without throwing on absent intermediates. */
export function pick(source, ...path) {
  let current = source
  for (const key of path) {
    if (current == null || typeof current !== 'object') return undefined
    current = current[key]
  }
  return current
}

/** Finite numbers only - never render NaN/Infinity. */
export function numberOrNull(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** Map an API confidence 0..1 to a whole percent, or null when absent. */
export function confidencePercent(value) {
  const n = numberOrNull(value)
  return n == null ? null : Math.round(n * 100)
}

/** ISO-8601 timestamps only; anything else is treated as unavailable. */
export function parseIso(value) {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (trimmed === '') return null
  const ms = Date.parse(trimmed)
  return Number.isFinite(ms) ? ms : null
}

/* ---------------------------------------------------------------- builders */

/** A label/value pair; omitted entirely when the API supplied no value. */
function metric(label, value, suffix = '') {
  if (value === null || value === undefined || value === '') return null
  return { label, value: `${value}${suffix}` }
}

const metrics = (list) => list.filter(Boolean)

/** Keep the API's own timestamp only when it really parses. */
const ts = (value) => (parseIso(value) == null ? null : value)

/** Join supplied phrases, dropping blanks; never invents connective claims. */
function describe(parts, fallback = null) {
  const kept = parts.filter((part) => typeof part === 'string' && part.trim() !== '')
  return kept.length ? kept.join(' ') : fallback
}

/** Fixed-decimal display string, so 12.0 renders as "12.0" and never as "12". */
function round(value, digits = 2) {
  const n = numberOrNull(value)
  return n == null ? null : n.toFixed(digits)
}

/**
 * The investigation timeline, built only from the two API responses the console
 * already holds.
 *
 * @returns {{events: object[], timed: object[], untimed: object[]}}
 *   `timed` is chronological (ascending, ties broken by id for determinism);
 *   `untimed` holds analysis steps whose payload carries no timestamp.
 */
export function buildTimeline(investigation, detection) {
  const events = []
  const origin = investigation?.origin || {}
  const region = origin.region || {}
  const releaseWindow = origin.releaseWindow || {}
  const drift = origin.drift || {}
  const stats = investigation?.statistics || {}
  const ranking = investigation?.ranking || {}
  const entries = Array.isArray(ranking.entries) ? ranking.entries : []
  const acquisition = pick(detection, 'acquisitionTime')

  const push = (event) =>
    events.push({
      scope: 'case',
      mmsi: null,
      vesselId: null,
      name: null,
      end: null,
      confidence: null,
      description: null,
      metrics: [],
      ...event,
    })

  /* --- 1. the case-input prior ----------------------------------------- */
  if (releaseWindow.start || releaseWindow.end) {
    push({
      id: 'release-window',
      at: ts(releaseWindow.start),
      end: ts(releaseWindow.end),
      status: EVIDENCE_STATUS.PRIOR,
      type: EVIDENCE_TYPE.MODEL,
      title: 'Candidate release window',
      description: describe([
        round(releaseWindow.durationHours, 1) != null
          ? `${round(releaseWindow.durationHours, 1)} h window supplied with the case as an explicit prior - it is not derived from the slick.`
          : null,
        releaseWindow.note,
      ]),
      source: SOURCE.RELEASE_WINDOW,
      metrics: metrics([
        metric('Basis', releaseWindow.source),
        metric('Starts', releaseWindow.hoursBeforeObservation?.start, ' h before observation'),
        metric('Ends', releaseWindow.hoursBeforeObservation?.end, ' h before observation'),
      ]),
    })
  }

  /* --- 2. backward drift (the model run) -------------------------------- */
  if (Object.keys(drift).length > 0) {
    push({
      id: 'backward-drift',
      at: ts(releaseWindow.start),
      end: ts(origin.observedAt),
      status: EVIDENCE_STATUS.MODELLED,
      type: EVIDENCE_TYPE.MODEL,
      title: 'Backward drift / hindcast',
      description: describe([
        drift.integration ? `${drift.integration}.` : null,
        numberOrNull(origin.sampleCount) != null
          ? `${origin.sampleCount} particle samples from ${origin.seedCount ?? '?'} seeds around the observed slick.`
          : null,
        drift.parametersArePrototypeValues
          ? 'Drift parameters are prototype values and are not scientifically validated.'
          : null,
      ]),
      source: SOURCE.DRIFT,
      metrics: metrics([
        metric('Integration', drift.integration),
        metric('Step', round(drift.config?.stepSeconds, 0), ' s'),
        metric('Samples', origin.sampleCount),
        metric('Seeds', origin.seedCount),
        metric('Windage', round(drift.windageCoefficient, 3)),
        metric('Region buffer', round(drift.regionBufferKm, 1), ' km'),
      ]),
    })
  }

  /* --- 3. probable origin region --------------------------------------- */
  if (region.geometry) {
    push({
      id: 'origin-region',
      at: ts(origin.observedAt),
      status: EVIDENCE_STATUS.MODELLED,
      type: EVIDENCE_TYPE.MODEL,
      title: 'Probable origin region',
      description: describe([
        region.method ? `${region.method}.` : null,
        region.notes?.[0] ? `${region.notes[0]}.` : null,
      ]),
      source: SOURCE.REGION,
      confidence: numberOrNull(region.confidence),
      metrics: metrics([
        metric('Area', round(region.areaKm2, 1), ' km²'),
        metric('Vertices', region.vertexCount),
        metric('Spread', round(region.spreadKm, 2), ' km'),
        metric('Model confidence', confidencePercent(region.confidence), '%'),
      ]),
    })
  }

  /* --- 4. the satellite observation itself ------------------------------ */
  if (detection && Object.keys(detection).length > 0) {
    push({
      id: 'satellite-observation',
      at: ts(acquisition) || ts(origin.observedAt),
      status: EVIDENCE_STATUS.OBSERVED,
      type: EVIDENCE_TYPE.SATELLITE,
      title: `Satellite observation${detection.spillId ? ` (${detection.spillId})` : ''}`,
      description: describe([
        detection.classification ? `Classified as ${detection.classification}.` : null,
        detection.meetsConfidenceThreshold === false
          ? 'Detection confidence is below the configured threshold - treat with caution.'
          : null,
        detection.detectionConfidenceNote,
      ]),
      source: SOURCE.DETECTION,
      confidence: numberOrNull(detection.detectionConfidence),
      metrics: metrics([
        metric('Sensor', detection.sensor?.name),
        metric('Detection confidence', confidencePercent(detection.detectionConfidence), '%'),
        metric('Label', detection.uiLabel || detection.datasetLabel),
      ]),
    })

    const characterisation = detection.characterisation || {}
    if (Object.keys(characterisation).length > 0) {
      push({
        id: 'slick-characterisation',
        at: ts(acquisition) || ts(origin.observedAt),
        status: EVIDENCE_STATUS.ANALYTICAL,
        type: EVIDENCE_TYPE.SATELLITE,
        title: 'Oil slick characterisation',
        description: describe([
          'Geometry and shape metrics recomputed from the observed slick polygon.',
          characterisation.orientationNote,
        ]),
        source: SOURCE.CHARACTERISATION,
        metrics: metrics([
          metric('Area', round(characterisation.areaKm2, 2), ' km²'),
          metric('Perimeter', round(characterisation.perimeterKm, 2), ' km'),
          metric('Length', round(characterisation.approximateLengthKm, 1), ' km'),
          metric('Width', round(characterisation.approximateWidthKm, 1), ' km'),
          metric('Orientation', round(characterisation.orientationDeg, 0), '°'),
          metric('Vertices', characterisation.vertexCount),
        ]),
      })
    }

    const lookAlike = detection.lookAlikeAssessment || {}
    if (Object.keys(lookAlike).length > 0) {
      push({
        id: 'look-alike',
        at: ts(acquisition) || ts(origin.observedAt),
        status: EVIDENCE_STATUS.ANALYTICAL,
        type: EVIDENCE_TYPE.SATELLITE,
        title: 'Look-alike assessment',
        description: describe([
          Array.isArray(lookAlike.checkedClasses) && lookAlike.checkedClasses.length
            ? `Assessed at run time: ${lookAlike.checkedClasses.join(', ')}.`
            : null,
          Array.isArray(lookAlike.notAssessedClasses) && lookAlike.notAssessedClasses.length
            ? `NOT assessed from this scene: ${lookAlike.notAssessedClasses.join(', ')}.`
            : null,
          lookAlike.notes?.[0],
        ]),
        source: SOURCE.LOOK_ALIKE,
        metrics: metrics([
          metric('Wind at centroid', round(lookAlike.windSpeedMs, 1), ' m/s'),
          metric('Low-wind threshold', round(lookAlike.thresholdMs, 1), ' m/s'),
          metric('Low-wind area', lookAlike.lowWindArea === true ? 'yes' : lookAlike.lowWindArea === false ? 'no' : null),
        ]),
      })
    }
  }

  /* --- 5. vessel-specific observations (real AIS timestamps only) ------- */
  for (const entry of entries) {
    const mmsi = entry.mmsi == null ? null : String(entry.mmsi)
    const compatibility = entry.compatibility || {}
    const gaps = entry.gapAnalysis || {}
    const behaviour = entry.behaviour || {}
    const base = {
      scope: 'vessel',
      mmsi,
      vesselId: entry.vesselId ?? null,
      name: entry.name ?? null,
    }
    const label = entry.name || (mmsi ? `MMSI ${mmsi}` : 'Unknown vessel')

    if (ts(compatibility.firstInsideTimestamp)) {
      push({
        ...base,
        id: `${mmsi}-first-inside`,
        at: ts(compatibility.firstInsideTimestamp),
        status: EVIDENCE_STATUS.OBSERVED,
        type: EVIDENCE_TYPE.AIS,
        title: `${label} recorded inside the origin region`,
        description: compatibility.insideRegionDuringWindow
          ? 'The first recorded AIS position inside the probable origin region falls while the release window was open.'
          : 'The first recorded AIS position inside the probable origin region falls outside the release window.',
        source: SOURCE.COMPATIBILITY,
        metrics: metrics([
          metric('Relation to window', compatibility.insideRegionRelation),
          metric('Min distance in window', round(compatibility.minDistanceKmDuringWindow, 2), ' km'),
          metric('Reports in window', compatibility.recordsInWindow),
        ]),
      })
    }

    const closest = compatibility.closestInWindow
    if (closest && ts(closest.timestamp)) {
      push({
        ...base,
        id: `${mmsi}-closest-approach`,
        at: ts(closest.timestamp),
        status: EVIDENCE_STATUS.OBSERVED,
        type: EVIDENCE_TYPE.AIS,
        title: `${label} closest approach in the window`,
        description:
          'Closest recorded AIS position to the estimated origin region while the release window was open.',
        source: SOURCE.COMPATIBILITY,
        metrics: metrics([
          metric('Distance to region', round(closest.distanceKm, 2), ' km'),
          metric(
            'Position',
            numberOrNull(closest.lat) != null && numberOrNull(closest.lon) != null
              ? `${round(closest.lat, 4)}, ${round(closest.lon, 4)}`
              : null,
          ),
          metric('Window coverage', confidencePercent(compatibility.plausibleSegmentFraction), '% plausible'),
        ]),
      })
    }

    const gapList = Array.isArray(gaps.gaps) ? gaps.gaps : []
    gapList.forEach((gap, index) => {
      push({
        ...base,
        id: `${mmsi}-gap-${index}`,
        at: ts(gap.start),
        end: ts(gap.end),
        status: EVIDENCE_STATUS.OBSERVED,
        type: EVIDENCE_TYPE.AIS,
        title: `${label} AIS broadcast gap`,
        description: describe([
          Array.isArray(gap.reasons) && gap.reasons.length ? `${gap.reasons.join('; ')}.` : null,
          gap.note,
        ]),
        source: SOURCE.GAPS,
        metrics: metrics([
          metric('Duration', round(gap.durationHours, 2), ' h'),
          metric('Straight-line distance', round(gap.straightLineKm, 1), ' km'),
          metric('Implied speed', round(gap.impliedSpeedKn, 1), ' kn'),
          metric('Own speed cap', round(gap.capSpeedKn, 1), ' kn'),
          metric('Physically feasible', gap.feasible === true ? 'yes' : gap.feasible === false ? 'no' : null),
          metric('Gap evidence value', round(gap.relevance, 2)),
        ]),
      })
    })

    if (behaviour.isAnomaly) {
      push({
        ...base,
        id: `${mmsi}-behaviour`,
        at: null,
        status: EVIDENCE_STATUS.ANALYTICAL,
        type: EVIDENCE_TYPE.AIS,
        title: `${label} behavioural anomaly`,
        description: describe([
          behaviour.description ? `${behaviour.description}.` : null,
          behaviour.note,
        ]),
        source: SOURCE.BEHAVIOUR,
        metrics: metrics([
          metric('Window median SOG', round(behaviour.window?.medianSogKn, 1), ' kn'),
          metric('Own baseline median', round(behaviour.baseline?.medianSogKn, 1), ' kn'),
          metric('Window slow fraction', confidencePercent(behaviour.window?.slowFraction), '%'),
          metric('Own baseline slow fraction', confidencePercent(behaviour.baseline?.slowFraction), '%'),
          metric('Raw anomaly', round(behaviour.rawAnomaly, 3)),
          metric('Scored anomaly', round(behaviour.scoredAnomaly, 3)),
        ]),
      })
    }
  }

  /* --- 6. pipeline steps the payload carries no timestamp for ----------- */
  if (numberOrNull(stats.recordsCleaned) != null || entries.length > 0) {
    push({
      id: 'ais-filtering',
      at: null,
      status: EVIDENCE_STATUS.ANALYTICAL,
      type: EVIDENCE_TYPE.AIS,
      title: 'Historical AIS filtering',
      description: describe([
        numberOrNull(stats.recordsCleaned) != null
          ? `${stats.recordsCleaned} cleaned AIS reports and ${entries.length} vessel tracks were correlated against the origin region and the release window.`
          : null,
        UNTIMED_NOTE,
      ]),
      source: SOURCE.STATISTICS,
      metrics: metrics([
        metric('Reports cleaned', stats.recordsCleaned),
        metric('Vessels scored', stats.vesselsScored),
        metric('Inside region in window', stats.insideRegionDuringWindow),
        metric('Gaps judged', stats.gapsJudged),
        metric('Behaviour anomalies', stats.behaviourAnomaliesReported),
      ]),
    })
  }

  const weights = investigation?.weights || {}
  if (Object.keys(weights).length > 0) {
    push({
      id: 'evidence-scoring',
      at: null,
      status: EVIDENCE_STATUS.ANALYTICAL,
      type: EVIDENCE_TYPE.SCORING,
      title: 'Evidence scoring',
      description: describe([
        'Every candidate is scored on the same five compatibility factors using the configured weights; the score is an evidence aggregation, not a probability of responsibility.',
        numberOrNull(stats.weightsTotal) != null ? `Configured weights total ${stats.weightsTotal}.` : null,
        UNTIMED_NOTE,
      ]),
      source: SOURCE.WEIGHTS,
      metrics: Object.entries(weights).map(([key, value]) => metric(key, round(value, 1))),
    })
  }

  if (entries.length > 0) {
    push({
      id: 'candidate-ranking',
      at: null,
      status: EVIDENCE_STATUS.ANALYTICAL,
      type: EVIDENCE_TYPE.SCORING,
      title: 'Candidate ranking',
      description: describe([
        ranking.orderingRule,
        Array.isArray(ranking.notes) ? ranking.notes[1] : null,
        UNTIMED_NOTE,
      ]),
      source: SOURCE.RANKING,
      metrics: metrics([
        metric('Candidates', entries.length),
        metric('Tie groups', stats.tieGroupCount),
        metric('Mean score', round(stats.meanScore, 1)),
        metric('Top candidate', stats.topCandidateMmsi),
      ]),
    })
  }

  /* --- ordering --------------------------------------------------------- */
  const timed = events
    .filter((event) => event.at != null)
    .sort((a, b) => parseIso(a.at) - parseIso(b.at) || a.id.localeCompare(b.id))
  const untimed = events.filter((event) => event.at == null)

  return { events, timed, untimed }
}

/**
 * A timeline row is emphasised when it belongs to the selected vessel. Case-level
 * events stay emphasised always: the global chronology remains the context.
 */
export function isEmphasised(event, mmsi) {
  if (event.scope === 'case') return true
  return mmsi != null && String(event.mmsi) === String(mmsi)
}

/** Earliest and latest recorded timestamps across a timeline's timed events. */
export function timelineRange(timeline) {
  const timed = Array.isArray(timeline?.timed) ? timeline.timed : []
  const starts = timed.map((event) => parseIso(event.at)).filter((n) => n != null)
  const ends = timed.map((event) => parseIso(event.end ?? event.at)).filter((n) => n != null)
  if (starts.length === 0 || ends.length === 0) return { start: null, end: null, spanHours: null }
  const start = Math.min(...starts)
  const end = Math.max(...ends)
  return { start, end, spanHours: Number(((end - start) / 3600000).toFixed(2)) }
}

/** Event count per status, used by the legend. */
export function countByStatus(timeline) {
  const counts = { OBSERVED: 0, PRIOR: 0, MODELLED: 0, ANALYTICAL: 0 }
  for (const event of timeline?.events || []) {
    if (Object.prototype.hasOwnProperty.call(counts, event.status)) counts[event.status] += 1
  }
  return counts
}

/**
 * The neutral case narrative, assembled only from API values. Uses candidate /
 * investigation-priority terminology and makes no claim about responsibility.
 */
export function summariseTimeline(investigation) {
  const origin = investigation?.origin || {}
  const region = origin.region || {}
  const releaseWindow = origin.releaseWindow || {}
  const stats = investigation?.statistics || {}
  const entries = Array.isArray(investigation?.ranking?.entries) ? investigation.ranking.entries : []
  const top = entries.find((entry) => entry.rank === 1) || null
  const lines = []

  if (numberOrNull(region.areaKm2) != null) {
    const confidence = confidencePercent(region.confidence)
    lines.push(
      `A probable origin region of ${round(region.areaKm2, 1)} km² was reconstructed by backward particle drift from the observed slick` +
        (confidence != null ? `, with a prototype model confidence of ${confidence}%.` : '.'),
    )
  }
  if (releaseWindow.start && releaseWindow.end) {
    lines.push(
      `The candidate release window is a case-input prior (${round(releaseWindow.durationHours, 1) ?? '—'} h) supplied with the case, not inferred from the slick.`,
    )
  }
  if (numberOrNull(stats.recordsCleaned) != null) {
    lines.push(
      `${stats.recordsCleaned} cleaned AIS reports across ${stats.vesselsScored ?? entries.length} vessels were correlated with the region and the window` +
        (numberOrNull(stats.insideRegionDuringWindow) != null
          ? `; ${stats.insideRegionDuringWindow} were inside the region while the window was open.`
          : '.'),
    )
  }
  if (top) {
    lines.push(
      `${top.name || `MMSI ${top.mmsi}`} (MMSI ${top.mmsi}) holds the highest investigation priority at ${round(top.totalScore, 1)} of 100 - an evidence aggregation used to order analyst review, not a probability of responsibility.`,
    )
  }
  if (numberOrNull(stats.tieGroupCount) != null && stats.tieGroupCount > 0) {
    lines.push(
      `${stats.tieGroupCount} group(s) of candidates share an identical score: the available evidence does not separate them, and their order is a display choice.`,
    )
  }
  return lines
}


