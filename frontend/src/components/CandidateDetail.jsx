import { factorRows, fmtDateTime, fmtDuration, fmtKm, fmtNumber, fmtPercent } from '../lib/format.js'
import { Badge, Card, Empty, NoticeList, Row, Stat } from './ui.jsx'

/**
 * Step 5 (right half): full evidence breakdown for the selected candidate -
 * every factor, the engine's own reason strings, behaviour vs own baseline,
 * AIS gaps, and the counterfactual ("why not the vessel nearest the slick?").
 */
export default function CandidateDetail({ entry, trajectory }) {
  if (!entry) {
    return (
      <Card id="candidate-detail" title="Candidate evidence" icon="🔍">
        <Empty>Select a vessel in the ranking to inspect its evidence breakdown.</Empty>
      </Card>
    )
  }

  const factors = factorRows(entry.factors)
  const compat = entry.compatibility || {}
  const behaviour = entry.behaviour || {}
  const gaps = entry.gapAnalysis || {}
  const counter = entry.counterfactual

  return (
    <Card
      id="candidate-detail"
      title={entry.name || `MMSI ${entry.mmsi}`}
      subtitle={`Rank ${entry.rank} · MMSI ${entry.mmsi} · ${entry.vesselType}`}
      icon="🔍"
      actions={<Badge tone="accent">{fmtNumber(entry.totalScore, 1)} / 100</Badge>}
    >
      <div className="stat-row">
        <Stat label="Total score" value={fmtNumber(entry.totalScore, 1)} sub="of 100" />
        <Stat label="Inside region" value={compat.insideRegionDuringWindow ? 'yes' : 'no'} sub={compat.insideRegionRelation} />
        <Stat label="Min distance" value={fmtKm(compat.minDistanceKmDuringWindow, 1)} sub="to origin region" />
        <Stat label="Window records" value={compat.recordsInWindow ?? '—'} sub={`${fmtNumber(compat.plausibleSegmentFraction * 100, 0)}% plausible`} />
      </div>

      <h3 className="sub-head">Evidence breakdown</h3>
      <div className="factor-list">
        {factors.map((f) => (
          <div className="factor-row" key={f.key}>
            <div className="factor-head">
              <strong>{f.label}</strong>
              <span className="mono">
                {fmtNumber(f.points, 1)} / {f.maxPoints}
              </span>
            </div>
            <div className="factor-bar">
              <div className="factor-fill" style={{ width: `${(f.percent * 100).toFixed(1)}%` }} />
            </div>
            <small>{f.hint}</small>
          </div>
        ))}
      </div>

      <h3 className="sub-head">Why the engine ranked it here</h3>
      <ul className="reason-list">
        {(entry.reasons || []).map((reason, i) => (
          <li key={i}>{reason}</li>
        ))}
      </ul>

      <div className="detail-columns">
        <div>
          <h3 className="sub-head">Behaviour vs own baseline</h3>
          <Row label="Anomaly" value={behaviour.isAnomaly ? 'yes' : 'no'} />
          <Row label="Raw anomaly" value={fmtNumber(behaviour.rawAnomaly, 3)} />
          <Row label="Scored" value={fmtNumber(behaviour.scoredAnomaly, 3)} sub={behaviour.scoredEligible ? 'eligible' : 'not scored (not in region)'} />
          <Row label="Description" value={behaviour.description || '—'} />
          <Row
            label="Window median SOG"
            value={`${fmtNumber(behaviour.window?.medianSogKn, 1)} kn`}
            hint={`own baseline ${fmtNumber(behaviour.baseline?.medianSogKn, 1)} kn`}
          />
          <Row label="Window slow fraction" value={fmtPercent(behaviour.window?.slowFraction, 0)} hint={`own baseline ${fmtPercent(behaviour.baseline?.slowFraction, 0)}`} />
        </div>

        <div>
          <h3 className="sub-head">AIS gap analysis</h3>
          <Row label="Has gap" value={gaps.hasGap ? `yes (${gaps.gapCount})` : 'no'} />
          <Row label="Feasible" value={gaps.anyFeasible ? 'yes' : 'no'} />
          <Row label="Relevant to window" value={gaps.anyRelevant ? 'yes' : 'no'} />
          <Row label="Best evidence value" value={fmtNumber(gaps.bestEvidenceValue, 3)} />
          <Row label="Speed cap" value={`${fmtNumber(gaps.capSpeedKn, 1)} kn`} />
          <NoticeList title="Gap notes" items={gaps.notes} />
        </div>
      </div>

      {counter ? (
        <div className="counterfactual">
          <h3 className="sub-head">Counterfactual — why not {counter.againstName}?</h3>
          <p>{counter.text}</p>
          <div className="delta-list">
            {Object.entries(counter.factorDeltas || {}).map(([key, delta]) => (
                <Badge key={key} tone={Number(delta) > 0 ? 'ok' : 'neutral'}>
                  {key} {Number(delta) > 0 ? '+' : ''}
                  {fmtNumber(delta, 1)}
                </Badge>
            ))}
          </div>
        </div>
      ) : null}

      {trajectory ? (
        <>
          <h3 className="sub-head">Reconstructed AIS track</h3>
          <Row label="Positions" value={trajectory.stats?.recordCount ?? '—'} />
          <Row label="First seen" value={fmtDateTime(trajectory.stats?.firstTimestamp)} />
          <Row label="Last seen" value={fmtDateTime(trajectory.stats?.lastTimestamp)} />
          <Row label="Duration" value={fmtDuration(trajectory.stats?.durationSeconds)} />
          <Row label="Observed distance" value={fmtKm(trajectory.stats?.observedDistanceKm, 1)} />
          <Row label="Average speed" value={`${fmtNumber(trajectory.stats?.averageSpeedKn, 1)} kn`} />
          <Row label="Max reported SOG" value={`${fmtNumber(trajectory.stats?.maxReportedSogKn, 1)} kn`} />
        </>
      ) : null}

      <NoticeList title="Compatibility notes" items={compat.notes} />
    </Card>
  )
}
