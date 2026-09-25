/**
 * Phase 17 - forensic evidence chain.
 *
 * Builds the investigator-facing "why this candidate?" chain. Every node is
 * derived from an existing API field and carries the `source` path it was read
 * from, so the chain stays auditable. Nothing is re-scored here: the five factor
 * values are the engine's own, passed through unchanged.
 *
 * The cascade mirrors the method: observed data -> modelled inference -> AIS
 * correlation -> evidence compatibility -> candidate ranking. An inferred or
 * modelled link is never presented as a direct observation.
 */
import { FACTOR_META, factorRows } from './format.js'
import { EVIDENCE_STATUS } from './timeline.js'

/** Prefixes the scoring engine uses for each factor's own reason string. */
export const REASON_PREFIX = Object.freeze({
  spatial: 'distance to origin region',
  temporal: 'proximity to release window',
  trajectory: 'course-change correlation',
  behaviour: 'stop/slow pattern',
  gap: 'AIS-gap behaviour',
})

/**
 * Map the engine's reason strings onto the five factors using those prefixes.
 * A factor that received no reason string stays null, so the UI can report that
 * the engine returned no explanation for it.
 */
export function reasonsByFactor(reasons) {
  const list = Array.isArray(reasons) ? reasons : []
  const out = {}
  for (const factor of FACTOR_META) {
    const prefix = REASON_PREFIX[factor.key].toLowerCase()
    out[factor.key] =
      list.find((reason) => typeof reason === 'string' && reason.toLowerCase().startsWith(prefix)) || null
  }
  return out
}

/** A label/value pair, omitted when the API supplied nothing. */
function fact(label, value, suffix = '') {
  if (value === null || value === undefined || value === '') return null
  return { label, value: `${value}${suffix}` }
}

const facts = (list) => list.filter(Boolean)

const num = (value) => (typeof value === 'number' && Number.isFinite(value) ? value : null)

const pct = (value) => {
  const n = num(value)
  return n == null ? null : Math.round(n * 100)
}

/** Fixed-decimal display string, so 12.0 renders as "12.0" and never as "12". */
const rnd = (value, digits = 2) => {
  const n = num(value)
  return n == null ? null : n.toFixed(digits)
}

/**
 * One evidence-chain node. `status` uses the same vocabulary as the timeline so
 * the two views cannot drift apart.
 */
function node({ id, title, status, source, summary = null, metrics = [], available = true, unavailableReason = null }) {
  return { id, title, status, source, summary, metrics, available, unavailableReason }
}

/** The five cascade layers, in order. */
export const LAYER_ORDER = Object.freeze([
  { id: 'observed', title: 'Observed data', caption: 'recorded by instruments' },
  { id: 'modelled', title: 'Modelled inference', caption: 'derived by the drift model' },
  { id: 'correlation', title: 'AIS correlation', caption: 'this candidate\u2019s recorded activity' },
  { id: 'compatibility', title: 'Evidence compatibility', caption: 'the engine\u2019s own factor scores' },
  { id: 'ranking', title: 'Candidate ranking', caption: 'priority order for analyst review' },
])

const MISSING = 'Not present in this API response.'

/**
 * Build the evidence chain for one candidate.
 *
 * @param {object} investigation    the /investigate payload's `investigation`
 * @param {object} detection        the /detect payload's `detection`
 * @param {string} mmsi             the selected candidate
 * @param {object|null} trajectory  that vessel's entry from /ais/trajectory
 */
export function buildEvidenceChain(investigation, detection, mmsi, trajectory = null) {
  const entries = Array.isArray(investigation?.ranking?.entries) ? investigation.ranking.entries : []
  const entry = entries.find((e) => String(e.mmsi) === String(mmsi)) || null
  if (!entry) return { available: false, reason: 'No ranked candidate matches the current selection.', layers: [] }

  const detected = detection || {}
  const origin = investigation?.origin || {}
  const region = origin.region || {}
  const releaseWindow = origin.releaseWindow || {}
  const stats = investigation?.statistics || {}
  const compatibility = entry.compatibility || {}
  const behaviour = entry.behaviour || {}
  const gapAnalysis = entry.gapAnalysis || {}
  const reasons = reasonsByFactor(entry.reasons)
  const factors = factorRows(entry.factors)
  const tieGroups = Array.isArray(investigation?.ranking?.tieGroups) ? investigation.ranking.tieGroups : []
  const tieGroup = tieGroups.find((group) => group.some((id) => String(id) === String(entry.mmsi))) || null
  const counterfactual = entry.counterfactual || null

  /* --- layer 1: observed ------------------------------------------------ */
  const observedNodes = []
  if (detected.acquisitionTime || detected.spillId) {
    observedNodes.push(
      node({
        id: 'n-satellite',
        title: `Satellite observation${detected.spillId ? ` ${detected.spillId}` : ''}`,
        status: EVIDENCE_STATUS.OBSERVED,
        source: 'detection',
        summary: detected.classification || null,
        metrics: facts([
          fact('Acquisition', detected.acquisitionTime),
          fact('Detection confidence', pct(detected.detectionConfidence), '%'),
        ]),
      }),
    )
  }
  const characterisation = detected.characterisation || {}
  if (Object.keys(characterisation).length > 0) {
    observedNodes.push(
      node({
        id: 'n-slick',
        title: 'Oil slick characterisation',
        status: EVIDENCE_STATUS.ANALYTICAL,
        source: 'detection.characterisation',
        summary: 'Shape and extent recomputed from the observed slick polygon.',
        metrics: facts([
          fact('Area', rnd(characterisation.areaKm2, 2), ' km²'),
          fact('Length', rnd(characterisation.approximateLengthKm, 1), ' km'),
          fact('Width', rnd(characterisation.approximateWidthKm, 1), ' km'),
          fact('Orientation', rnd(characterisation.orientationDeg, 0), '°'),
        ]),
      }),
    )
  }
  const lookAlike = detected.lookAlikeAssessment || {}
  if (Object.keys(lookAlike).length > 0) {
    observedNodes.push(
      node({
        id: 'n-lookalike',
        title: 'Look-alike assessment',
        status: EVIDENCE_STATUS.ANALYTICAL,
        source: 'detection.lookAlikeAssessment',
        summary:
          Array.isArray(lookAlike.checkedClasses) && lookAlike.checkedClasses.length
            ? `Checked: ${lookAlike.checkedClasses.join(', ')}. Not assessed from this scene: ${(lookAlike.notAssessedClasses || []).join(', ')}.`
            : null,
        metrics: facts([
          fact('Wind at centroid', rnd(lookAlike.windSpeedMs, 1), ' m/s'),
          fact('Low-wind threshold', rnd(lookAlike.thresholdMs, 1), ' m/s'),
          fact(
            'Warning',
            lookAlike.lookAlikeWarning === true ? 'raised' : lookAlike.lookAlikeWarning === false ? 'not raised' : null,
          ),
        ]),
      }),
    )
  }
  if (num(stats.recordsCleaned) != null) {
    observedNodes.push(
      node({
        id: 'n-ais-reports',
        title: 'Historical AIS reporting',
        status: EVIDENCE_STATUS.OBSERVED,
        source: 'investigation.statistics',
        summary: 'Cleaned AIS reports were grouped into per-vessel tracks before any compatibility test.',
        metrics: facts([
          fact('Reports cleaned', stats.recordsCleaned),
          fact('Vessels', stats.vesselsScored),
        ]),
      }),
    )
  }

  /* --- layer 2: modelled inference ------------------------------------- */
  const modelledNodes = []
  const drift = origin.drift || {}
  if (Object.keys(drift).length > 0) {
    modelledNodes.push(
      node({
        id: 'n-drift',
        title: 'Backward drift / hindcast',
        status: EVIDENCE_STATUS.MODELLED,
        source: 'origin.drift',
        summary: [
          drift.integration ? `${drift.integration}.` : null,
          drift.parametersArePrototypeValues
            ? 'Prototype parameters, not scientifically validated.'
            : null,
        ]
          .filter(Boolean)
          .join(' ') || null,
        metrics: facts([
          fact('Step', rnd(drift.config?.stepSeconds, 0), ' s'),
          fact('Samples', origin.sampleCount),
          fact('Seeds', origin.seedCount),
          fact('Windage', rnd(drift.windageCoefficient, 3)),
        ]),
      }),
    )
  }
  if (region.geometry) {
    modelledNodes.push(
      node({
        id: 'n-region',
        title: 'Probable origin region',
        status: EVIDENCE_STATUS.MODELLED,
        source: 'origin.region',
        summary: region.method || null,
        metrics: facts([
          fact('Area', rnd(region.areaKm2, 1), ' km²'),
          fact('Vertices', region.vertexCount),
          fact('Spread', rnd(region.spreadKm, 2), ' km'),
          fact('Model confidence', pct(region.confidence), '%'),
        ]),
      }),
    )
  } else {
    modelledNodes.push(
      node({
        id: 'n-region',
        title: 'Probable origin region',
        status: EVIDENCE_STATUS.MODELLED,
        source: 'origin.region',
        available: false,
        unavailableReason: MISSING,
      }),
    )
  }
  if (releaseWindow.start || releaseWindow.end) {
    modelledNodes.push(
      node({
        id: 'n-window',
        title: 'Candidate release window',
        status: EVIDENCE_STATUS.PRIOR,
        source: 'origin.releaseWindow',
        summary: releaseWindow.note || null,
        metrics: facts([
          fact('Start', releaseWindow.start),
          fact('End', releaseWindow.end),
          fact('Duration', rnd(releaseWindow.durationHours, 1), ' h'),
          fact('Basis', releaseWindow.source),
        ]),
      }),
    )
  }

  /* --- layer 3: AIS correlation (candidate-specific) -------------------- */
  const correlationNodes = []
  const trackStats = trajectory?.stats || null
  if (trackStats) {
    correlationNodes.push(
      node({
        id: 'n-track',
        title: 'Reconstructed vessel track',
        status: EVIDENCE_STATUS.OBSERVED,
        source: 'trajectory.stats',
        summary: 'Grouped, time-sorted AIS positions for this vessel; no leg is drawn across a gap.',
        metrics: facts([
          fact('Positions', trackStats.recordCount),
          fact('First seen', trackStats.firstTimestamp),
          fact('Last seen', trackStats.lastTimestamp),
          fact('Observed distance', rnd(trackStats.observedDistanceKm, 1), ' km'),
          fact('Average speed', rnd(trackStats.averageSpeedKn, 1), ' kn'),
          fact('Max reported SOG', rnd(trackStats.maxReportedSogKn, 1), ' kn'),
        ]),
      }),
    )
  } else {
    correlationNodes.push(
      node({
        id: 'n-track',
        title: 'Reconstructed vessel track',
        status: EVIDENCE_STATUS.OBSERVED,
        source: 'trajectory.stats',
        available: false,
        unavailableReason: 'The /ais/trajectory bundle is not loaded for this vessel.',
      }),
    )
  }

  correlationNodes.push(
    node({
      id: 'n-spatial',
      title: 'Spatial relation to the origin region',
      status: EVIDENCE_STATUS.ANALYTICAL,
      source: 'ranking[].compatibility',
      summary:
        compatibility.insideRegionDuringWindow === true
          ? 'Recorded inside the probable origin region while the release window was open.'
          : compatibility.insideRegionAnytime === true
            ? 'Recorded inside the probable origin region, but not while the window was open.'
            : 'Not recorded inside the probable origin region.',
      metrics: facts([
        fact('Relation', compatibility.insideRegionRelation),
        fact('Min distance in window', rnd(compatibility.minDistanceKmDuringWindow, 2), ' km'),
        fact('Min distance whole track', rnd(compatibility.minDistanceKmWholeTrack, 2), ' km'),
        fact(
          'Closest in window',
          compatibility.closestInWindow?.timestamp
            ? `${compatibility.closestInWindow.timestamp} at ${rnd(compatibility.closestInWindow.distanceKm, 2)} km`
            : null,
        ),
      ]),
    }),
  )

  correlationNodes.push(
    node({
      id: 'n-temporal',
      title: 'Presence during the release window',
      status: EVIDENCE_STATUS.ANALYTICAL,
      source: 'ranking[].compatibility',
      summary:
        num(compatibility.windowPresenceSeconds) != null && num(compatibility.windowCoverageSeconds) != null
          ? `${Math.round((compatibility.windowPresenceSeconds / compatibility.windowCoverageSeconds) * 100)}% of the window is covered by recorded positions in the region.`
          : null,
      metrics: facts([
        fact('Reports in window', compatibility.recordsInWindow),
        fact('Segments in window', compatibility.segmentsInWindow),
        fact('Plausible segments', compatibility.plausibleSegmentsInWindow),
        fact('Own speed cap', rnd(compatibility.speedCapKn, 1), ' kn'),
      ]),
    }),
  )

  correlationNodes.push(
    node({
      id: 'n-behaviour',
      title: 'Behaviour versus own baseline',
      status: EVIDENCE_STATUS.ANALYTICAL,
      source: 'ranking[].behaviour',
      summary: behaviour.description || behaviour.note || null,
      metrics: facts([
        fact('Anomaly', behaviour.isAnomaly === true ? 'flagged' : behaviour.isAnomaly === false ? 'not flagged' : null),
        fact('Window median SOG', rnd(behaviour.window?.medianSogKn, 1), ' kn'),
        fact('Own baseline median', rnd(behaviour.baseline?.medianSogKn, 1), ' kn'),
        fact('Window slow fraction', pct(behaviour.window?.slowFraction), '%'),
        fact('Own baseline slow fraction', pct(behaviour.baseline?.slowFraction), '%'),
        fact('Raw anomaly', rnd(behaviour.rawAnomaly, 3)),
        fact('Scored anomaly', rnd(behaviour.scoredAnomaly, 3)),
      ]),
    }),
  )

  const gapList = Array.isArray(gapAnalysis.gaps) ? gapAnalysis.gaps : []
  if (gapList.length === 0) {
    correlationNodes.push(
      node({
        id: 'n-gaps',
        title: 'AIS broadcast gaps',
        status: EVIDENCE_STATUS.OBSERVED,
        source: 'ranking[].gapAnalysis',
        summary:
          gapAnalysis.hasGap === false
            ? 'No broadcast gap was recorded for this vessel. The absence of a gap is not evidence either.'
            : null,
        metrics: facts([
          fact('Gaps', gapAnalysis.gapCount),
          fact('Own speed cap', rnd(gapAnalysis.capSpeedKn, 1), ' kn'),
        ]),
      }),
    )
  } else {
    gapList.forEach((gap, index) => {
      correlationNodes.push(
        node({
          id: `n-gap-${index}`,
          title: `AIS broadcast gap${gapList.length > 1 ? ` ${index + 1}` : ''}`,
          status: EVIDENCE_STATUS.OBSERVED,
          source: 'ranking[].gapAnalysis.gaps[]',
          summary: Array.isArray(gap.reasons) && gap.reasons.length ? `${gap.reasons.join('; ')}.` : gap.note || null,
          metrics: facts([
            fact('From', gap.start),
            fact('To', gap.end),
            fact('Duration', rnd(gap.durationHours, 2), ' h'),
            fact('Straight-line distance', rnd(gap.straightLineKm, 1), ' km'),
            fact('Implied speed', rnd(gap.impliedSpeedKn, 1), ' kn'),
            fact('Own speed cap', rnd(gap.capSpeedKn, 1), ' kn'),
            fact('Physically feasible', gap.feasible === true ? 'yes' : gap.feasible === false ? 'no' : null),
            fact('Gap evidence value', rnd(gap.relevance, 2)),
          ]),
        }),
      )
    })
  }

  /* --- layer 4: evidence compatibility (the engine's own numbers) ------- */
  const compatibilityNodes = factors.map((factor) => ({
    ...node({
      id: `n-factor-${factor.key}`,
      title: factor.label,
      status: EVIDENCE_STATUS.ANALYTICAL,
      source: `ranking[].factors.${factor.key}`,
      summary: reasons[factor.key] || 'The engine returned no reason string for this factor.',
      metrics: facts([
        fact('Points', `${rnd(factor.points, 1)} of ${factor.maxPoints}`),
        fact('Share of its cap', Math.round(factor.percent * 100), '%'),
        fact('Engine detail', factor.detail ? JSON.stringify(factor.detail) : null),
      ]),
    }),
    factorKey: factor.key,
    points: factor.points,
    maxPoints: factor.maxPoints,
    percent: factor.percent,
    supported: factor.points > 0,
  }))

  /* --- layer 5: candidate ranking --------------------------------------- */
  const rankingNodes = [
    node({
      id: 'n-rank',
      title: `Rank ${entry.rank ?? '—'} of ${entries.length} candidates`,
      status: EVIDENCE_STATUS.ANALYTICAL,
      source: 'ranking.entries[]',
      summary: investigation?.ranking?.orderingRule || null,
      metrics: facts([
        fact('Investigation priority', rnd(entry.totalScore, 1), ' of 100'),
        fact('Distance to slick at observation', rnd(entry.distanceToSlickKm, 1), ' km'),
        fact('Tie group', tieGroup ? `${tieGroup.length} candidates share this score` : null),
      ]),
    }),
  ]

  if (counterfactual) {
    rankingNodes.push(
      node({
        id: 'n-counterfactual',
        title: `Why not ${counterfactual.againstName || counterfactual.againstMmsi || 'the comparison vessel'}?`,
        status: EVIDENCE_STATUS.ANALYTICAL,
        source: 'ranking[].counterfactual',
        summary: counterfactual.text || null,
        metrics: facts(
          Object.entries(counterfactual.factorDeltas || {}).map(([key, delta]) =>
            fact(key, `${Number(delta) > 0 ? '+' : ''}${rnd(delta, 3)}`),
          ),
        ),
      }),
    )
  } else {
    rankingNodes.push(
      node({
        id: 'n-counterfactual',
        title: 'Counterfactual comparison',
        status: EVIDENCE_STATUS.ANALYTICAL,
        source: 'ranking[].counterfactual',
        available: false,
        unavailableReason: 'Counterfactual comparison unavailable.',
      }),
    )
  }

  const layers = [
    observedNodes,
    modelledNodes,
    correlationNodes,
    compatibilityNodes,
    rankingNodes,
  ]
    .map((nodes, index) => ({ ...LAYER_ORDER[index], nodes }))
    .filter((layer) => layer.nodes.length > 0)

  // Flattened views of the same data. The component renders straight from
  // `layers`; these two derived arrays exist so other consumers (the Phase 18
  // report) can read the chain without re-deriving its structure.
  const nodes = layers.flatMap((layer) => (layer.nodes || []).map((node) => ({ ...node, layerId: layer.id })))
  // One link per adjacent layer pair - the same relationship the component
  // draws as an arrow between layer blocks.
  const edges = layers.slice(0, -1).map((layer, index) => ({
    id: `${layer.id}->${layers[index + 1].id}`,
    fromLayer: layer.id,
    toLayer: layers[index + 1].id,
    fromNodeCount: (layer.nodes || []).length,
    toNodeCount: (layers[index + 1].nodes || []).length,
  }))

  return {
    available: true,
    mmsi: String(entry.mmsi),
    vesselId: entry.vesselId ?? null,
    name: entry.name ?? null,
    rank: entry.rank ?? null,
    totalScore: num(entry.totalScore),
    layers,
    nodes,
    edges,
    factors: compatibilityNodes,
    counterfactual: {
      available: Boolean(counterfactual),
      text: counterfactual?.text ?? null,
      againstName: counterfactual?.againstName ?? null,
      againstMmsi: counterfactual?.againstMmsi ?? null,
      deltas: counterfactual?.factorDeltas ?? null,
    },
    tieGroup: tieGroup ? { size: tieGroup.length } : null,
    narrative: chainNarrative(entry, region, releaseWindow, compatibility, counterfactual),
  }
}

/**
 * The candidate's chain narrative, in cascade order. Every clause is built from
 * the values passed in - nothing is asserted that the API did not return.
 * Wording stays neutral: candidates and investigation priority, never guilt.
 */
export function chainNarrative(entry, region, releaseWindow, compatibility, counterfactual) {
  const lines = []

  if (rnd(region?.areaKm2, 1) != null) {
    lines.push(
      `Observed slick → the probable origin region was reconstructed as a region of ${rnd(region.areaKm2, 1)} km²` +
        (pct(region.confidence) != null ? ` (prototype model confidence ${pct(region.confidence)}%).` : '.'),
    )
  }
  if (releaseWindow?.start && releaseWindow?.end) {
    lines.push(
      `Release window → ${releaseWindow.start} to ${releaseWindow.end} (${rnd(releaseWindow.durationHours, 1)} h), supplied as a case-input prior.`,
    )
  }

  if (compatibility?.insideRegionDuringWindow === true) {
    lines.push(
      'Historical AIS correlation → this candidate was recorded inside the probable origin region while the release window was open.',
    )
  } else if (compatibility?.insideRegionAnytime === true) {
    lines.push(
      'Historical AIS correlation → this candidate entered the probable origin region, but not while the release window was open.',
    )
  } else {
    lines.push(
      'Historical AIS correlation → this candidate was not recorded inside the probable origin region during the release window.',
    )
  }

  const behaviour = entry?.behaviour || {}
  if (behaviour.isAnomaly === true && behaviour.scoredEligible === true) {
    lines.push(
      `Vessel behaviour → a behavioural anomaly of ${rnd(behaviour.rawAnomaly, 2)} was detected against this vessel's own baseline and scored, because the vessel was present in the region.`,
    )
  } else if (behaviour.isAnomaly === true) {
    lines.push(
      `Vessel behaviour → a behavioural anomaly of ${rnd(behaviour.rawAnomaly, 2)} was detected, but it is reported as context only: the vessel was outside the region during the window.`,
    )
  }

  const gaps = Array.isArray(entry?.gapAnalysis?.gaps) ? entry.gapAnalysis.gaps : []
  if (gaps.length > 0) {
    const gap = gaps[0]
    lines.push(
      gap.feasible === true
        ? `AIS gap → ${rnd(gap.durationHours, 2)} h of missing broadcasts requires ${rnd(gap.impliedSpeedKn, 1)} kn against a ${rnd(gap.capSpeedKn, 1)} kn cap, so the gap is physically feasible. A gap is contextual evidence, not proof of anything.`
        : `AIS gap → ${rnd(gap.durationHours, 2)} h of missing broadcasts would require ${rnd(gap.impliedSpeedKn, 1)} kn against a ${rnd(gap.capSpeedKn, 1)} kn cap, which is not physically feasible, so the gap contributes no evidence value.`,
    )
  }

  if (rnd(entry?.totalScore, 1) != null) {
    lines.push(
      `Evidence compatibility → investigation priority ${rnd(entry.totalScore, 1)} of 100 at rank ${entry.rank ?? '—'}. This score aggregates compatible evidence; it is not a probability of responsibility.`,
    )
  }
  if (counterfactual?.text) {
    lines.push(`Ranking comparison → ${counterfactual.text}`)
  }
  return lines
}
