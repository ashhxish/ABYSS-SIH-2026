import { fmtConfidence, fmtDateTime, fmtNumber } from '../lib/format.js'
import { Badge, Spinner } from './ui.jsx'

/** Console context: case identity, observation time, provenance and demo status. */
export default function Header({ investigation, detection, health, loading, onReload }) {
  const caseId = investigation?.caseId || detection?.caseId || health?.demoCaseId || '—'
  const dataset = investigation?.datasetLabel || detection?.datasetLabel || health?.dataMode || '—'
  const source = detection?.dataSource || investigation?.source?.provider || 'intelligence service'
  const observedAt = investigation?.observedAt || detection?.acquisitionTime
  const centroid = detection?.characterisation?.centroid
  const region = investigation?.origin?.region
  const releaseWindow = investigation?.origin?.releaseWindow
  const location = centroid
    ? `${fmtNumber(centroid.lat, 4)}°N, ${fmtNumber(centroid.lon, 4)}°E`
    : '—'
  const release = releaseWindow?.start && releaseWindow?.end
    ? `${fmtDateTime(releaseWindow.start)} → ${fmtDateTime(releaseWindow.end)}`
    : '—'

  return (
    <header className="app-header">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">◈</div>
        <div>
          <h1>ABYSS Intelligence Console</h1>
          <p className="brand-sub">Maritime oil-spill origin reconstruction &amp; evidence review</p>
        </div>
      </div>

      <div className="case-strip">
        <div className="case-chip">
          <span className="case-chip-label">Case</span>
          <span className="case-chip-value mono">{caseId}</span>
        </div>
        <div className="case-chip">
          <span className="case-chip-label">Slick</span>
          <span className="case-chip-value mono">{detection?.spillId || '—'}</span>
        </div>
        <div className="case-chip">
          <span className="case-chip-label">Observed</span>
          <span className="case-chip-value">{fmtDateTime(observedAt)}</span>
        </div>
        <div className="case-chip">
          <span className="case-chip-label">Dataset</span>
          <span className="case-chip-value">{dataset}</span>
        </div>
        <Badge tone={investigation?.synthetic ? 'demo' : 'ok'}>
          {investigation?.synthetic ? 'SYNTHETIC DEMO DATA' : 'LIVE DATA'}
        </Badge>
        <button className="btn" onClick={onReload} disabled={loading}>
          {loading ? <Spinner label="Refreshing" /> : 'Refresh case'}
        </button>
      </div>

      <div className="case-context" aria-label="Investigation context">
        <div>
          <span className="context-label">Observed slick location</span>
          <strong className="mono">{location}</strong>
        </div>
        <div>
          <span className="context-label">Probable origin region</span>
          <strong>{fmtConfidence(region?.confidence)} origin confidence</strong>
        </div>
        <div>
          <span className="context-label">Release time window</span>
          <strong>{release}</strong>
        </div>
      </div>

      <p className="source-line">
        Source: <span className="mono">{source}</span>
        {investigation?.disclaimer ? <> · {investigation.disclaimer}</> : null}
      </p>
    </header>
  )
}

