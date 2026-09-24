import { factorRows, fmtKm, fmtNumber, fmtPercent, rankingEntries, scoreBand } from '../lib/format.js'
import { Badge, Bar, Card, Empty, Stat } from './ui.jsx'

/**
 * Step 5 (left half): the ranked candidate list.
 * Every number is the API's own score - the console does not re-weight anything.
 */
export default function CandidateTable({ investigation, selected, onSelect }) {
  const entries = rankingEntries(investigation)
  const stats = investigation?.statistics || {}

  return (
    <Card
      id="candidates"
      title="Ranked candidate vessels"
      subtitle="Multi-factor evidence score, highest first"
      icon="🎯"
      actions={
        <span className="muted">
          weights:{' '}
          {Object.entries(investigation?.weights || {})
            .map(([k, v]) => `${k} ${v}`)
            .join(' · ')}
        </span>
      }
    >
      <div className="stat-row">
        <Stat label="Vessels scored" value={stats.vesselsScored ?? entries.length} />
        <Stat label="Mean score" value={fmtNumber(stats.meanScore, 1)} />
        <Stat label="Inside region in window" value={stats.insideRegionDuringWindow ?? '—'} />
        <Stat label="Gaps judged" value={stats.gapsJudged ?? '—'} />
        <Stat label="Top vessel" value={stats.topCandidateMmsi ? stats.topCandidateMmsi : '—'} mono />
      </div>

      {entries.length === 0 ? (
        <Empty>No candidates returned by the scoring engine.</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>#</th>
                <th>Vessel</th>
                <th>Score</th>
                <th>Evidence factors</th>
                <th>Region</th>
                <th>To slick</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => {
                const band = scoreBand(entry.totalScore)
                const isSelected = String(selected) === String(entry.mmsi)
                const factors = factorRows(entry.factors)
                return (
                  <tr
                    key={entry.mmsi}
                    className={isSelected ? 'row-selected' : ''}
                    onClick={() => onSelect(entry.mmsi)}
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && onSelect(entry.mmsi)}
                  >
                    <td className="rank-cell">{entry.rank}</td>
                    <td className="vessel-cell">
                      <div className="vessel-name">{entry.name || `MMSI ${entry.mmsi}`}</div>
                      <div className="vessel-meta mono">
                        {entry.mmsi} · {entry.vesselType}
                      </div>
                    </td>
                    <td className="score-cell">
                      <div className="score-line">
                        <strong>{fmtNumber(entry.totalScore, 1)}</strong>
                        <Badge tone={band.tone}>{band.label}</Badge>
                      </div>
                      <Bar
                        percent={Number(entry.totalScore) / 100}
                        tone={band.tone}
                        label={`${fmtNumber(entry.totalScore, 1)} of 100`}
                      />
                    </td>
                    <td className="factors-cell">
                      <div className="factor-mini">
                        {factors.map((f) => (
                          <div className="factor-mini-item" key={f.key} title={`${f.label}: ${fmtNumber(f.points, 1)} / ${f.maxPoints}`}>
                            <span className="factor-mini-label">{f.key.slice(0, 3).toUpperCase()}</span>
                            <Bar percent={f.percent} tone={f.percent > 0.6 ? 'accent' : f.percent > 0 ? 'muted' : 'empty'} />
                            <span className="factor-mini-value">{fmtNumber(f.points, 0)}</span>
                          </div>
                        ))}
                      </div>
                    </td>
                    <td>
                      {entry.compatibility?.insideRegionDuringWindow ? (
                        <Badge tone="ok">inside in window</Badge>
                      ) : entry.compatibility?.insideRegionAnytime ? (
                        <Badge tone="low">inside outside window</Badge>
                      ) : (
                        <Badge tone="neutral">outside</Badge>
                      )}
                    </td>
                    <td className="mono nowrap">{fmtKm(entry.distanceToSlickKm, 1)}</td>
                    <td>
                      <div className="flag-stack">
                        {entry.behaviour?.isAnomaly ? <Badge tone="warn">behaviour</Badge> : null}
                        {entry.gapAnalysis?.hasGap ? <Badge tone="warn">gap</Badge> : null}
                        {!entry.behaviour?.isAnomaly && !entry.gapAnalysis?.hasGap ? (
                          <span className="muted">—</span>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="fine-print">
        Score is an evidence aggregation, <strong>not a probability of guilt</strong>.{' '}
        {investigation?.ranking?.orderingRule}
      </p>
    </Card>
  )
}
