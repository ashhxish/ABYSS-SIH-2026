import { Card, Row, Stat, Badge, Spinner, KeyValueTable } from './ui.jsx'
import { fmtNumber, fmtLatLon, fmtIso, fmtInt } from '../lib/format.js'
import Sentinel1Panel from './Sentinel1Panel.jsx'

/**
 * DetectionStagePanel handles Stage 01: DETECT
 * In Real mode: Renders Sentinel-1 SAR previews, VV/VH bands, U-Net mask, statistics, and provenance.
 * In CASE-001 mode: Renders synthetic Sentinel-1 SAR polygon characteristics.
 */
export default function DetectionStagePanel({
  isRealMode,
  detection,
  s1Data,
  loading,
  error,
  onRetry,
  realAis,
  onContinue,
}) {
  if (isRealMode) {
    return (
      <div className="stage-panel-detect">
        <Sentinel1Panel
          data={s1Data}
          loading={loading}
          error={error}
          onRetry={onRetry}
          realAis={realAis}
        />
        {(() => {
          const s1Obs = s1Data?.observation || {}
          const s1Res = s1Data?.result || {}
          const s1Char = s1Obs.characteristics || {}
          const areaKm2 = s1Res.area_km2 ?? s1Char.areaKm2 ?? null
          const oilFrac = s1Res.oil_fraction ?? null
          const centroid = s1Res.centroid || s1Char.centroid || null
          return (
          <div
            className="investigator-interpretation-card"
            style={{
              marginTop: '16px',
              padding: '16px 20px',
              backgroundColor: 'rgba(14, 45, 74, 0.4)',
              border: '1px solid var(--accent-subtle)',
              borderRadius: 'var(--radius)',
            }}
          >
            <h4 style={{ color: 'var(--accent)', margin: '0 0 8px 0', fontSize: '14px' }}>
              🔬 INVESTIGATOR INTERPRETATION
            </h4>
            <p style={{ margin: '0 0 10px 0', fontSize: '13px', lineHeight: 1.5 }}>
              Detected slick geometry established via U-Net deep segmentation on C-band VV/VH imagery.
              Temporal attribution remains unavailable because acquisition timestamp is missing from the GeoTIFF metadata.
            </p>
            <div style={{ display: 'flex', gap: '20px', fontSize: '12px', color: 'var(--text-dim)' }}>
              <div><strong>Detected Area:</strong> {areaKm2 != null ? `${fmtNumber(areaKm2, 2)} km²` : '—'}</div>
              <div><strong>Oil Fraction:</strong> {oilFrac != null ? `${fmtNumber(oilFrac * 100, 3)}% of scene` : '—'}</div>
              <div><strong>Slick Centroid:</strong> {centroid ? fmtLatLon(centroid.lat, centroid.lon, 4) : '—'}</div>
              <div><strong>Oil Pixels:</strong> {s1Res.oil_pixel_count != null ? fmtInt(s1Res.oil_pixel_count) : '—'}</div>
            </div>
          </div>
          )
        })()}
        <div className="stage-actions" style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end' }}>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onContinue}
            disabled={!s1Data && loading}
          >
            CONTINUE TO ORIGIN →
          </button>
        </div>
      </div>
    )
  }

  // CASE-001 live detection shapes: acquisitionTime, characterisation {areaKm2,
  // perimeterKm, centroid {lat, lon}, boundingBox {minLat…}, geometry},
  // classification, detectionConfidence, sensor, provenance.
  const acq = detection?.acquisitionTime
  const char = detection?.characterisation || {}
  const centroid = char.centroid || {}
  const bboxObj = char.boundingBox || {}
  const bboxList = [
    bboxObj.minLon ?? bboxObj.west,
    bboxObj.minLat ?? bboxObj.south,
    bboxObj.maxLon ?? bboxObj.east,
    bboxObj.maxLat ?? bboxObj.north,
  ]
  const bboxOk = bboxList.every((v) => v !== null && v !== undefined && Number.isFinite(Number(v)))

  return (
    <div className="stage-panel-detect">
      <Card
        id="synthetic-detection"
        title="SAR Slick Detection & Characterization (CASE-001)"
        subtitle="Synthetic baseline observation with calibrated geometry"
        icon="🛰️"
      >
        {loading ? (
          <Spinner label="Loading detection baseline..." />
        ) : error ? (
          <div className="callout callout-danger">
            <p>{error}</p>
            <button className="btn" onClick={onRetry}>Retry</button>
          </div>
        ) : (
          <div>
            <Row>
              <Stat label="Source Platform" value={detection?.sensor?.name || 'Sentinel-1 SAR'} />
              <Stat label="Sensor Mode" value={detection?.sensor?.band || 'IW / GRD'} />
              <Stat label="Estimated Slick Area" value={`${fmtNumber(char.areaKm2, 2)} km²`} />
              <Stat label="Perimeter" value={`${fmtNumber(char.perimeterKm, 2)} km`} />
            </Row>

            <div style={{ marginTop: '16px' }}>
              <KeyValueTable
                rows={[
                  { key: 'Observation Timestamp', value: fmtIso(acq) },
                  { key: 'Slick Centroid', value: centroid.lat != null ? fmtLatLon(centroid.lat, centroid.lon, 4) : '—' },
                  { key: 'Bounding Box', value: bboxOk ? `[${bboxList.map((v) => fmtNumber(v, 4)).join(', ')}]` : '—' },
                  { key: 'Classification', value: detection?.classification || '—' },
                  { key: 'Detection Confidence', value: detection?.detectionConfidence != null ? `${fmtNumber(detection.detectionConfidence * 100, 1)}%` : '—' },
                  { key: 'Provenance', value: detection?.provenance || detection?.dataSource || '—' },
                ]}
              />
            </div>

            <div
              className="investigator-interpretation-card"
              style={{
                marginTop: '16px',
                padding: '14px 18px',
                backgroundColor: 'rgba(56, 189, 248, 0.08)',
                borderLeft: '4px solid var(--accent)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <h4 style={{ color: 'var(--accent)', margin: '0 0 6px 0', fontSize: '13px' }}>
                INVESTIGATOR INTERPRETATION
              </h4>
              <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-dim)', lineHeight: 1.5 }}>
                Slick boundary and acquisition stamp{acq ? ` (${acq})` : ''} are read live from the detection response.
                This baseline feeds the reverse hydrodynamic hindcast and vessel correlation stages.
              </p>
            </div>
          </div>
        )}
      </Card>

      <div className="stage-actions" style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end' }}>
        <button type="button" className="btn btn-primary" onClick={onContinue}>
          CONTINUE TO ORIGIN →
        </button>
      </div>
    </div>
  )
}
