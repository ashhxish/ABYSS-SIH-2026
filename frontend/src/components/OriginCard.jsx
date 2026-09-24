import { fmtConfidence, fmtDateTime, fmtInt, fmtKm, fmtNumber } from '../lib/format.js'
import { Badge, Card, Gauge, NoticeList, Row, Stat } from './ui.jsx'

/**
 * Step 3: the probable release region and the candidate release window.
 * The region is a polygon with a confidence value, never a single point - the UI
 * states that explicitly, matching the API contract.
 */
export default function OriginCard({ investigation }) {
  const origin = investigation?.origin
  if (!origin) return null
  const region = origin.region || {}
  const window = origin.releaseWindow || {}
  const drift = origin.drift || {}
  const bounds = region.bounds || {}

  return (
    <Card
      id="origin"
      title="Probable release region"
      subtitle="Backward particle drift of the observed slick — a REGION, never a point estimate"
      icon="🧭"
      actions={<Badge tone="accent">{region.vertexCount || 0}-vertex polygon</Badge>}
    >
      <div className="origin-grid">
        <div className="gauge-block">
          <Gauge value={region.confidence} label="Origin confidence" caption="model confidence" />
          <Stat label="Region area" value={`${fmtNumber(region.areaKm2, 1)} km²`} sub={`spread ${fmtNumber(region.spreadKm, 1)} km`} />
        </div>

        <div className="fact-block">
          <h3 className="sub-head">Release time window</h3>
          <Row label="Window opens" value={fmtDateTime(window.start)} />
          <Row label="Window closes" value={fmtDateTime(window.end)} />
          <Row label="Duration" value={`${fmtNumber(window.durationHours, 1)} h`} />
          <Row
            label="Before observation"
            value={window.hoursBeforeObservation
              ? `${fmtNumber(window.hoursBeforeObservation.start, 1)} h – ${fmtNumber(window.hoursBeforeObservation.end, 1)} h`
              : null}
          />
          <Row label="Window source" value={window.source} />
          <p className="fine-print">{window.note}</p>

          <h3 className="sub-head">Region extent</h3>
          <Row
            label="Latitude"
            mono
            value={`${fmtNumber(bounds.minLat, 3)} – ${fmtNumber(bounds.maxLat, 3)}`}
          />
          <Row
            label="Longitude"
            mono
            value={`${fmtNumber(bounds.minLon, 3)} – ${fmtNumber(bounds.maxLon, 3)}`}
          />
          <Row label="Method" value={region.method} />
        </div>
      </div>

      <div className="drift-strip">
        <div><span>Particles</span><strong>{fmtInt(origin.seedCount)}</strong><small>seeds × {fmtInt(origin.sampleCount)} snapshots</small></div>
        <div><span>Drift integration</span><strong>{drift.integration || '—'}</strong></div>
        <div><span>Windage</span><strong>{fmtNumber(drift.windageCoefficient, 3)}</strong><small>{drift.windageSource}</small></div>
        <div><span>Step</span><strong>{fmtNumber(drift.stepSeconds, 0)} s</strong><small>sample every {fmtNumber(drift.sampleHours, 1)} h</small></div>
        <div><span>Buffer</span><strong>{fmtNumber(drift.regionBufferKm, 1)} km</strong><small>positional safety margin</small></div>
      </div>

      <NoticeList
        title="Model notes"
        items={[...(region.notes || []), ...(origin.notes || [])]}
      />
      {drift.parametersArePrototypeValues ? (
        <p className="fine-print warn-text">
          Drift parameters are prototype values, not calibrated constants.
        </p>
      ) : null}
    </Card>
  )
}
