import {
  fmtConfidence,
  fmtDateTime,
  fmtInt,
  fmtKm,
  fmtLatLon,
  fmtLatitude,
  fmtLongitude,
  fmtNumber,
  fmtPercent,
} from '../lib/format.js'
import { Badge, Card, Gauge, NoticeList, Row, Spinner, Stat } from './ui.jsx'

/**
 * Step 1 + 2: what the satellite saw. All values come from GET/POST /detect.
 * The look-alike panel is deliberately prominent - a slick detection is a
 * candidate, not a confirmed spill.
 */
export default function ObservationCard({ detection, loading, error, onRetry }) {
  if (loading && !detection) {
    return <Card id="observation" title="Satellite observation" subtitle="Loading detection…"><Spinner /></Card>
  }
  if (error && !detection) {
    return (
      <Card id="observation" title="Satellite observation">
        <p className="error-text">{error}</p>
        <button className="btn" onClick={onRetry}>Retry</button>
      </Card>
    )
  }
  if (!detection) return null

  const char = detection.characterisation || {}
  const look = detection.lookAlikeAssessment || {}
  const sensor = detection.sensor || {}

  return (
    <Card
      id="observation"
      title="Satellite observation"
      subtitle={`${detection.classification || 'Classification pending'} · ${sensor.band || 'sensor band not reported'}`}
      icon="🛰️"
      actions={
        <Badge tone={detection.detected ? 'ok' : 'warn'}>
          {detection.detected ? 'SLICK CANDIDATE DETECTED' : 'NO DETECTION'}
        </Badge>
      }
    >
      <div className="observation-grid">
        <div className="gauge-block">
          <Gauge
            value={detection.detectionConfidence}
            label="Detection confidence"
            caption="model confidence"
          />
          <p className="fine-print">{detection.detectionConfidenceNote}</p>
        </div>

        <div className="fact-block">
          <div className="stat-row">
            <Stat label="Area" value={`${fmtNumber(char.areaKm2, 2)} km²`} sub={`${fmtKm(char.perimeterKm, 1)} perimeter`} />
            <Stat label="Orientation" value={`${fmtNumber(char.orientationDeg, 0)}°`} sub={char.orientationNote ? 'major axis' : 'not reported'} />
            <Stat label="Vertices" value={fmtInt(char.vertexCount)} sub="polygon points" />
          </div>
          <Row label="Acquisition" value={fmtDateTime(detection.acquisitionTime)} />
          <Row label="Centroid" mono value={char.centroid ? fmtLatLon(char.centroid.lat, char.centroid.lon, 4) : null} />
          <Row
            label="Bounding box"
            mono
            value={char.boundingBox
              ? `lat ${fmtLatitude(char.boundingBox.minLat, 3)}–${fmtLatitude(char.boundingBox.maxLat, 3)} · lon ${fmtLongitude(char.boundingBox.minLon, 3)}–${fmtLongitude(char.boundingBox.maxLon, 3)}`
              : null}
          />
          <Row label="Length × width" value={`${fmtNumber(char.approximateLengthKm, 1)} × ${fmtNumber(char.approximateWidthKm, 1)} km`} />
        </div>
      </div>

      <div className="lookalike">
        <div className="lookalike-head">
          <h3>Look-alike screening</h3>
          <Badge tone={detection.lookAlikeWarning ? 'warn' : 'ok'}>
            {detection.lookAlikeWarning ? 'LOOK-ALIKE NOT EXCLUDED' : 'no warning raised'}
          </Badge>
        </div>
        <Row label="Wind at slick" value={`${fmtNumber(look.windSpeedMs, 1)} m/s`} hint={`threshold ${fmtNumber(look.thresholdMs, 1)} m/s`} />
        <Row label="Low-wind area" value={look.lowWindArea === undefined ? '—' : String(look.lowWindArea)} />
        <Row
          label="Not assessed"
          value={(look.notAssessedClasses || []).join(', ') || 'none'}
          hint="These classes cannot be excluded from a single synthetic scene"
        />
        <Row label="Classes considered" value={(look.classesConsidered || []).join(', ') || '—'} />
        <NoticeList title="Assessment notes" items={look.notes} />
      </div>

      <NoticeList title="Detection warnings" items={detection.warnings || []} />
      <p className="fine-print">Provenance: {detection.provenance}</p>
    </Card>
  )
}
