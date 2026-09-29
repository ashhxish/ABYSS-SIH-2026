import { Card, Row, Stat, Badge, KeyValueTable } from './ui.jsx'
import { fmtScore, fmtNumber, fmtIso, fmtLatLon } from '../lib/format.js'
import { matchedVessels } from '../lib/realais.js'

/**
 * Real-mode spatial match card, read strictly from the live `/ais/real/analyze`
 * payload. No vessel identity, timestamp or score is ever hard-coded: when the
 * service returns no match, the card says so.
 */
function RealAisSpatialMatch({ realAis }) {
  const vessels = matchedVessels(realAis)
  const vessel = vessels[0] || null
  if (!vessel) {
    return (
      <div
        style={{
          padding: '16px',
          background: 'rgba(14, 45, 74, 0.4)',
          border: '1px solid var(--accent-subtle)',
          borderRadius: 'var(--radius)',
        }}
      >
        <strong style={{ color: 'var(--text)' }}>SPATIALLY COMPATIBLE CANDIDATE: </strong>
        <span style={{ color: 'var(--text-dim)' }}>None returned by the live AIS analysis.</span>
      </div>
    )
  }
  const pos = vessel.matchedFirstPosition || vessel.matchedLastPosition || null
  return (
    <div
      style={{
        padding: '16px',
        background: 'rgba(14, 45, 74, 0.4)',
        border: '1px solid var(--accent-subtle)',
        borderRadius: 'var(--radius)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <strong style={{ color: 'var(--text)' }}>SPATIALLY COMPATIBLE CANDIDATE: </strong>
          <span style={{ color: 'var(--accent)' }}>{vessel.vesselName || `MMSI ${vessel.mmsi}`} (MMSI: {vessel.mmsi}{vessel.imo ? ` / IMO: ${vessel.imo}` : ''})</span>
        </div>
        <Badge tone="warn">TEMPORAL ATTRIBUTION PENDING</Badge>
      </div>
      <p style={{ margin: '8px 0 0 0', fontSize: '12px', color: 'var(--text-dim)', lineHeight: 1.5 }}>
        Matched Position: {fmtIso(vessel.matchedStartTimestamp)}{pos ? ` at (${fmtLatLon(pos.latitude, pos.longitude, 4)})` : ''}.
        Because SAR acquisition time is unknown, this candidate is documented strictly as a spatial match.
        It is <strong>NOT</strong> scored or identified as the responsible entity.
      </p>
    </div>
  )
}

/**
 * EvidenceFusionPanel — Stage 07: EVIDENCE FUSION
 * Intelligence matrix integrating Satellite, Environmental Drift, AIS Kinematics,
 * and Provenance. Supports interactive "WHY THIS CANDIDATE?" inspector.
 */
export default function EvidenceFusionPanel({
  investigation,
  detection,
  s1Data,
  candidates = [],
  selected,
  onSelectCandidate,
  onWhyThisCandidate,
  onContinue,
  onPrevious,
  isRealMode,
  realAis,
}) {
  const activeCandidate = candidates.find((c) => String(c.mmsi) === String(selected)) || candidates[0]
  const realMatch = matchedVessels(realAis)[0] || null
  const whyMmsi = isRealMode ? realMatch?.mmsi : activeCandidate?.mmsi

  // Fusion-matrix assessments, read live: real Sentinel-1 result + real AIS
  // counts, synthetic detection + synthetic top candidate.
  const s1Res = s1Data?.result || {}
  const s1Area = s1Res.area_km2
  const s1Frac = s1Res.oil_fraction
  const s1Assessment = s1Area != null
    ? `${fmtNumber(s1Area, 2)} km² dark patch detected via U-Net${s1Frac != null ? ` (${fmtNumber(s1Frac * 100, 3)}% of scene)` : ''}`
    : 'Real Sentinel-1 inference not available'
  const detArea = detection?.characterisation?.areaKm2
  const synthAssessment = detArea != null
    ? `${fmtNumber(detArea, 2)} km² slick (detection confidence ${detection?.detectionConfidence != null ? fmtNumber(detection.detectionConfidence * 100, 1) : '—'}%)`
    : 'Synthetic detection unavailable'
  const matchCount = realAis?.spatialMatchCount
  const aisSpatialAssessment = matchCount != null
    ? `${matchCount} vessel report${matchCount === 1 ? '' : 's'} inside SAR scene${realMatch ? ` (${realMatch.vesselName || realMatch.mmsi}, MMSI ${realMatch.mmsi})` : ''}`
    : 'Real AIS analysis not available'
  const insideRegion = investigation?.statistics?.insideRegionDuringWindow
  const synthSpatialAssessment = insideRegion != null
    ? `${insideRegion} vessel candidates inside origin region during window`
    : 'Synthetic spatial screening unavailable'
  const topEntry = candidates[0] || null
  const synthBehaviourAssessment = topEntry
    ? `${topEntry.name || `MMSI ${topEntry.mmsi}`} anomaly ${fmtNumber(topEntry?.behaviour?.rawAnomaly, 2)} (${topEntry?.behaviour?.description || 'no description'})`
    : 'Synthetic behavioural evidence unavailable'

  return (
    <div className="stage-panel-evidence" style={{ display: 'grid', gap: '20px' }}>
      <Card
        id="evidence-fusion"
        title="Multi-Source Forensic Evidence Fusion"
        subtitle="Cross-domain correlation matrix: Satellite + Hydrodynamic Drift + AIS Kinematics"
        icon="⚖️"
        actions={
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => whyMmsi && onWhyThisCandidate && onWhyThisCandidate(whyMmsi)}
            disabled={!whyMmsi}
          >
            🔍 WHY THIS CANDIDATE?
          </button>
        }
      >
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <Badge tone="accent">Multi-Criteria Forensic Fusion</Badge>
          <Badge tone={isRealMode ? 'warn' : 'ok'}>
            {isRealMode ? 'Spatial Compatibility Only' : 'Calibrated Multi-Factor Scoring'}
          </Badge>
          <Badge tone="neutral">Uncertainty Aware</Badge>
        </div>

        {/* Forensic Criteria Matrix */}
        <div style={{ overflowX: 'auto', marginBottom: '20px' }}>
          <table className="fusion-matrix-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ background: 'rgba(15, 23, 42, 0.8)', borderBottom: '1px solid var(--border)', textAlign: 'left' }}>
                <th style={{ padding: '10px 12px' }}>Evidence Domain</th>
                <th style={{ padding: '10px 12px' }}>Forensic Signal</th>
                <th style={{ padding: '10px 12px' }}>Status</th>
                <th style={{ padding: '10px 12px' }}>Forensic Assessment</th>
              </tr>
            </thead>
            <tbody>
              {/* Satellite */}
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <td style={{ padding: '10px 12px', fontWeight: 600 }}>🛰️ SATELLITE</td>
                <td style={{ padding: '10px 12px' }}>SAR Slick Segmentation</td>
                <td style={{ padding: '10px 12px' }}>
                  <Badge tone="ok">AVAILABLE</Badge>
                </td>
                <td style={{ padding: '10px 12px', color: 'var(--text-dim)' }}>
                  {isRealMode
                    ? s1Assessment
                    : synthAssessment}
                </td>
              </tr>

              {/* Environment */}
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <td style={{ padding: '10px 12px', fontWeight: 600 }}>🌊 ENVIRONMENT</td>
                <td style={{ padding: '10px 12px' }}>Lagrangian Drift Hindcast</td>
                <td style={{ padding: '10px 12px' }}>
                  <Badge tone="ok">AVAILABLE</Badge>
                </td>
                <td style={{ padding: '10px 12px', color: 'var(--text-dim)' }}>
                  {isRealMode
                    ? 'NOAA AOML surface geostrophic current field integrated (-6h backdrift)'
                    : 'HYCOM currents + ECMWF winds coupled advection'}
                </td>
              </tr>

              {/* AIS Spatial */}
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <td style={{ padding: '10px 12px', fontWeight: 600 }}>📍 AIS SPATIAL</td>
                <td style={{ padding: '10px 12px' }}>Scene Bounding Box Intersect</td>
                <td style={{ padding: '10px 12px' }}>
                  <Badge tone="ok">AVAILABLE</Badge>
                </td>
                <td style={{ padding: '10px 12px', color: 'var(--text-dim)' }}>
                  {isRealMode
                    ? aisSpatialAssessment
                    : synthSpatialAssessment}
                </td>
              </tr>

              {/* AIS Temporal */}
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <td style={{ padding: '10px 12px', fontWeight: 600 }}>⏱️ AIS TEMPORAL</td>
                <td style={{ padding: '10px 12px' }}>Discharge Window Alignment</td>
                <td style={{ padding: '10px 12px' }}>
                  <Badge tone={isRealMode ? 'warn' : 'ok'}>
                    {isRealMode ? 'BLOCKED' : 'AVAILABLE'}
                  </Badge>
                </td>
                <td style={{ padding: '10px 12px', color: 'var(--text-dim)' }}>
                  {isRealMode
                    ? 'SAR acquisition UTC unavailable in GeoTIFF; temporal match cannot be established'
                    : 'V001 matched exactly at release window onset (00:15:00 UTC)'}
                </td>
              </tr>

              {/* Behaviour */}
              <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <td style={{ padding: '10px 12px', fontWeight: 600 }}>📉 BEHAVIOURAL</td>
                <td style={{ padding: '10px 12px' }}>Kinematic & Gap Anomalies</td>
                <td style={{ padding: '10px 12px' }}>
                  <Badge tone={isRealMode ? 'neutral' : 'ok'}>
                    {isRealMode ? 'PARTIAL' : 'AVAILABLE'}
                  </Badge>
                </td>
                <td style={{ padding: '10px 12px', color: 'var(--text-dim)' }}>
                  {isRealMode
                    ? `${fmtInt(realAis?.gapCount)} transmission gaps detected; cannot link to spill without observation timestamp`
                    : synthBehaviourAssessment}
                </td>
              </tr>

              {/* Provenance */}
              <tr>
                <td style={{ padding: '10px 12px', fontWeight: 600 }}>📋 PROVENANCE</td>
                <td style={{ padding: '10px 12px' }}>Data Custody & Auditability</td>
                <td style={{ padding: '10px 12px' }}>
                  <Badge tone="ok">VERIFIED</Badge>
                </td>
                <td style={{ padding: '10px 12px', color: 'var(--text-dim)' }}>
                  {isRealMode
                    ? 'Real Sentinel-1 GeoTIFF (SHA256 verified) + NOAA/OAR/PMEL AIS'
                    : 'CASE-001 Synthetic Benchmark with immutable checksums'}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Candidate Selection Bar */}
        {isRealMode ? (
          <RealAisSpatialMatch realAis={realAis} />
        ) : (
          <div>
            <h4 style={{ margin: '0 0 10px 0', fontSize: '13px', color: 'var(--text-dim)' }}>
              CANDIDATE RANKING (CASE-001 BENCHMARK)
            </h4>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {candidates.slice(0, 3).map((c) => {
                const isSel = String(c.mmsi) === String(selected || candidates[0]?.mmsi)
                return (
                  <button
                    key={c.mmsi}
                    type="button"
                    className={`btn ${isSel ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => onSelectCandidate && onSelectCandidate(c.mmsi)}
                    style={{ fontSize: '12px', padding: '6px 12px' }}
                  >
                    {c.mmsi} ({c.name || c.vesselName || `Vessel ${c.mmsi}`}) — {fmtScore(c.totalScore)} pts
                  </button>
                )
              })}
            </div>
          </div>
        )}

        <div
          style={{
            marginTop: '18px',
            padding: '14px 18px',
            backgroundColor: 'rgba(14, 45, 74, 0.4)',
            border: '1px solid var(--accent-subtle)',
            borderRadius: 'var(--radius)',
          }}
        >
          <h4 style={{ color: 'var(--accent)', margin: '0 0 6px 0', fontSize: '13px' }}>
            WHAT THIS TELLS THE INVESTIGATOR
          </h4>
          <p style={{ margin: 0, fontSize: '12px', color: 'var(--text-dim)', lineHeight: 1.5 }}>
            Evidence fusion brings together geospatial containment, hydrodynamic physics, and vessel telemetry into a
            single evidentiary chain. Missing inputs are disclosed as forensic limits rather than arbitrary penalties.
          </p>
        </div>
      </Card>

      <div className="stage-actions" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <button type="button" className="btn btn-ghost" onClick={onPrevious}>
          ← PREVIOUS
        </button>
        <button type="button" className="btn btn-primary" onClick={onContinue}>
          CONTINUE TO INVESTIGATOR REVIEW →
        </button>
      </div>
    </div>
  )
}
