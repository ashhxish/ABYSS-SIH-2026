import { fmtInt, fmtNumber, scoreBand } from '../lib/format.js'
import { Card, Gauge, NoticeList, Stat } from './ui.jsx'

/**
 * Investigation confidence context: the origin model's confidence, the top
 * candidate's compatibility score, and the API's stated limitations.
 * These are analytical outputs on synthetic demo data, not a legal standard.
 */
export default function ConfidencePanel({ investigation }) {
  if (!investigation) return null
  const stats = investigation.statistics || {}
  const top = investigation.ranking?.entries?.[0]
  const band = scoreBand(top?.totalScore)

  return (
    <Card
      id="confidence"
      title="Investigation confidence context"
      subtitle="What the model is confident about — and what it is not"
      icon="📊"
    >
      <div className="confidence-grid">
        <div className="gauge-block">
          <Gauge value={stats.originConfidence} label="Origin" caption="region confidence" />
        </div>
        <div className="gauge-block">
          <Gauge
            value={Number(top?.totalScore || 0) / 100}
            label="Top candidate"
            caption="compatibility score"
          />
        </div>
        <div className="fact-block">
          <div className="stat-row">
            <Stat label="Top vessel" value={top?.name || '—'} sub={top ? `MMSI ${top.mmsi}` : ''} />
            <Stat label="Investigation priority" value={fmtNumber(top?.totalScore, 1)} sub={band.label} />
            <Stat label="Mean compatibility" value={fmtNumber(stats.meanScore, 1)} sub={`${fmtInt(stats.vesselsScored)} vessels`} />
            <Stat label="Tie groups" value={fmtInt(stats.tieGroupCount)} />
          </div>
          <NoticeList tone="warn" title="Stated limitations" items={investigation.limitations} />
        </div>
      </div>
      <p className="fine-print">
        Origin confidence and candidate compatibility are model outputs for the
        synthetic CASE-001 scene. They support investigation prioritisation; they do
        not establish scientific accuracy or legal responsibility.
      </p>
    </Card>
  )
}
