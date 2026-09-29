import { fmtConfidence, fmtDateTime, fmtLatLon, fmtNumber } from '../lib/format.js'
import { Badge, Spinner } from './ui.jsx'

/** Console context: case identity, observation time, provenance and demo status. */
export default function Header({
  investigation,
  detection,
  health,
  loading,
  onReload,
  viewMode = 'case-001',
  onSelectViewMode,
  s1Loading = false,
  s1Data = null,
}) {
  const isS1 = viewMode === 'sentinel1'

  // Labels strictly partitioned by view mode to ensure NO CASE-001 or synthetic markers bleed into the real view
  const caseId = isS1
    ? s1Data?.observation?.caseId || 'CASE-REAL-001'
    : investigation?.caseId || detection?.caseId || health?.demoCaseId || '—'

  const dataset = isS1
    ? 'Real Sentinel-1 C-SAR Acquisition (U-Net)'
    : investigation?.datasetLabel || detection?.datasetLabel || health?.dataMode || '—'

  const source = isS1
    ? '00999.tif (Sentinel-1 SAR) · best_unet_oil_spill.pth'
    : detection?.dataSource || investigation?.source?.provider || 'intelligence service'

  const observedAt = isS1 ? null : investigation?.observedAt || detection?.acquisitionTime

  const s1Centroid = s1Data?.result?.centroid
  // fmtLatLon applies the correct hemisphere (°W for these western longitudes);
  // interpolating a raw negative longitude with a "°E" suffix would mislabel it.
  const location = isS1
    ? s1Centroid
      ? fmtLatLon(s1Centroid.lat, s1Centroid.lon, 4)
      : 'Loading real coordinates…'
    : detection?.characterisation?.centroid
    ? fmtLatLon(detection.characterisation.centroid.lat, detection.characterisation.centroid.lon, 4)
    : '—'

  const region = investigation?.origin?.region
  const releaseWindow = investigation?.origin?.releaseWindow
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
        <div className="view-mode-selector" style={{ marginLeft: 'auto', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button
            type="button"
            className={`btn ${viewMode === 'case-001' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => onSelectViewMode && onSelectViewMode('case-001')}
          >
            CASE-001 DEMO
          </button>
          <button
            type="button"
            id="btn-real-sentinel1"
            className={`btn ${viewMode === 'sentinel1' ? 'btn-primary' : ''}`}
            style={{
              borderColor: viewMode === 'sentinel1' ? 'var(--accent)' : 'var(--border)',
              background: viewMode === 'sentinel1' ? 'linear-gradient(180deg, #0e3b5e, #09253d)' : 'var(--panel)',
            }}
            onClick={() => onSelectViewMode && onSelectViewMode('sentinel1')}
            disabled={s1Loading}
          >
            {s1Loading ? <Spinner label="Running U-Net..." /> : '🛰️ REAL SENTINEL-1 INVESTIGATION'}
          </button>
        </div>
      </div>

      <div className="case-strip">
        <div className="case-chip">
          <span className="case-chip-label">Case</span>
          <span className="case-chip-value mono">{caseId}</span>
        </div>
        <div className="case-chip">
          <span className="case-chip-label">Slick</span>
          <span className="case-chip-value mono">{isS1 ? s1Data?.observation?.spillId || 'SPILL-00999' : detection?.spillId || '—'}</span>
        </div>
        <div className="case-chip">
          <span className="case-chip-label">Observed</span>
          <span className="case-chip-value">{isS1 ? 'Unavailable in source metadata' : fmtDateTime(observedAt)}</span>
        </div>
        <div className="case-chip">
          <span className="case-chip-label">Dataset</span>
          <span className="case-chip-value">{dataset}</span>
        </div>
        <Badge tone={isS1 ? 'ok' : investigation?.synthetic ? 'demo' : 'ok'}>
          {isS1 ? 'REAL SENTINEL-1' : investigation?.synthetic ? 'SYNTHETIC DEMO DATA' : 'LIVE DATA'}
        </Badge>
        {!isS1 && (
          <button className="btn" onClick={onReload} disabled={loading}>
            {loading ? <Spinner label="Refreshing" /> : 'Refresh case'}
          </button>
        )}
      </div>

      <div className="case-context" aria-label="Investigation context">
        <div>
          <span className="context-label">Observed slick location</span>
          <strong className="mono">{location}</strong>
        </div>
        <div>
          <span className="context-label">{isS1 ? 'Attribution status' : 'Probable origin region'}</span>
          <strong>{isS1 ? 'Not available (pending AIS correlation)' : `${fmtConfidence(region?.confidence)} origin confidence`}</strong>
        </div>
        <div>
          <span className="context-label">Release time window</span>
          <strong>{isS1 ? 'Not available' : release}</strong>
        </div>
      </div>

      <p className="source-line">
        Source: <span className="mono">{source}</span>
        {isS1 ? (
          <> · Sentinel-1 detection is based on the supplied SAR scene and trained U-Net model. This view does not yet establish vessel responsibility. AIS correlation and environmental drift analysis are separate forensic stages.</>
        ) : investigation?.disclaimer ? (
          <> · {investigation.disclaimer}</>
        ) : null}
      </p>
    </header>
  )
}


