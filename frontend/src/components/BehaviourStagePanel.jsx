import { Card, Row, Stat, Badge, KeyValueTable } from './ui.jsx'
import { fmtNumber, fmtSpeed, fmtInt } from '../lib/format.js'
import { matchedVessels } from '../lib/realais.js'

/**
 * BehaviourStagePanel — Stage 06: BEHAVIOURAL FORENSICS
 * Analyzes kinematic anomalies, speed deviations, loitering, and AIS transponder gaps.
 * Strictly adheres to data honesty: when observation timestamp is unavailable,
 * behavioural correlation is reported as BLOCKED/UNAVAILABLE rather than fabricated.
 */
export default function BehaviourStagePanel({
  investigation,
  selected,
  trajectory,
  candidate,
  onContinue,
  onPrevious,
  isRealMode,
  realAis,
}) {
  const behaviour = candidate?.behaviour || {}
  const compat = candidate?.compatibility || {}
  const gapAnalysis = candidate?.gapAnalysis || {}
  const inspected = candidate || null

  // Real-mode values strictly from the live `/ais/real/analyze` payload.
  // Missing values render as '—' or honest "pending" states — never fallbacks.
  const rawCount = realAis?.rawRecordCount ?? null
  const acceptedCount = realAis?.acceptedRecordCount ?? null
  const vesselTotal = realAis?.uniqueMmsiCount ?? null
  const realTrajectoryCount = realAis?.trajectoryCount ?? null
  const realGapCount = realAis?.gapCount ?? null
  const realWarningCount = realAis?.warningCount ?? null
  const realMatch = matchedVessels(realAis)[0] || null
  const matchCount = realAis?.spatialMatchCount ?? null

  return (
    <div className="stage-panel-behaviour" style={{ display: 'grid', gap: '20px' }}>
      <Card
        id="behaviour-forensics"
        title="Vessel Kinematics & Behavioural Forensics"
        subtitle="Detection of transponder silencing, speed anomalies, loitering, and route deviations"
        icon="📉"
      >
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <Badge tone={isRealMode ? 'warn' : 'accent'}>
            {isRealMode ? 'Real NOAA AIS Extract' : 'Calibrated AIS Kinematics'}
          </Badge>
          <Badge tone={isRealMode ? 'neutral' : 'ok'}>
            {isRealMode ? 'Temporal Alignment: BLOCKED' : 'Full Trajectory Correlated'}
          </Badge>
          <Badge tone="accent">Gap Analysis Active</Badge>
        </div>

        {isRealMode ? (
          <div>
            {/* Real Forensic State Summary */}
            <Row>
              <Stat label="AIS Tracks Reconstructed" value={realTrajectoryCount != null ? `${fmtInt(realTrajectoryCount)} Tracks` : '—'} hint={rawCount != null ? `Across ${fmtInt(rawCount)} reports` : 'Run the AIS analysis'} />
              <Stat label="Reporting Gaps Detected" value={realGapCount != null ? `${fmtInt(realGapCount)} Gaps` : '—'} hint="Live gap count" />
              <Stat label="Temporal Alignment" value="UNAVAILABLE" hint="SAR timestamp missing" />
              <Stat label="Speed / Loitering Score" value="BLOCKED" hint="Zero-fabrication rule" />
            </Row>

            <div style={{ marginTop: '16px' }}>
              <KeyValueTable
                rows={[
                  { key: 'AIS Data Quality Status', value: realAis ? `${fmtInt(acceptedCount)} accepted${realAis.rejectedRecordCount != null ? `, ${fmtInt(realAis.rejectedRecordCount)} rejected` : ''}` : '—' },
                  { key: 'MMSI Identity Reporting', value: vesselTotal != null ? `${fmtInt(vesselTotal)} unique MMSIs` : '—' },
                  { key: 'Spatial Match In SAR Scene', value: realAis ? `${matchCount != null ? fmtInt(matchCount) : '—'} vessel position match${matchCount === 1 && realMatch ? ` (MMSI ${realMatch.mmsi}${realMatch.vesselName ? ` / ${realMatch.vesselName}` : ''})` : ''}` : '—' },
                  { key: 'Ingest Warnings', value: realWarningCount != null ? fmtInt(realWarningCount) : '—' },
                  {
                    key: 'Kinematic Behaviour Status',
                    value: (
                      <span style={{ color: 'var(--warn)', fontWeight: 600 }}>
                        TEMPORAL ATTRIBUTION BLOCKED
                      </span>
                    ),
                  },
                  {
                    key: 'Root Cause',
                    value: 'Spill observation timestamp unavailable in Sentinel-1 GeoTIFF metadata',
                  },
                ]}
              />
            </div>

            {/* Next Unlock Callout Card */}
            <div
              className="next-unlock-card"
              style={{
                marginTop: '16px',
                padding: '16px 20px',
                background: 'rgba(14, 45, 74, 0.4)',
                border: '1px solid var(--accent)',
                borderRadius: 'var(--radius)',
              }}
            >
              <h4 style={{ color: 'var(--accent)', margin: '0 0 8px 0', fontSize: '13px' }}>
                🔓 FORENSIC REQUIREMENTS TO UNLOCK BEHAVIOURAL ATTRIBUTION
              </h4>
              <p style={{ margin: '0 0 10px 0', fontSize: '12px', color: 'var(--text-dim)', lineHeight: 1.5 }}>
                Providing an explicit Sentinel-1 acquisition UTC timestamp in the ingestion pipeline will automatically enable:
              </p>
              <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '12px', color: 'var(--text)', lineHeight: 1.6 }}>
                <li><strong>Temporal Window Filtering:</strong> Exact slice matching AIS positions at observation time.</li>
                <li><strong>Speed Anomaly Analysis:</strong> Correlating engine slowdown (SOG reduction) with discharge physics.</li>
                <li><strong>Loitering & Drift Alignment:</strong> Distinguishing active maneuvering from passive drifting.</li>
                <li><strong>Approach / Departure Kinematics:</strong> Calculating trajectory entry and egress vectors relative to slick origin.</li>
                <li><strong>Gapsilence Forensics:</strong> Correlating transponder transmission dropouts with spill location.</li>
              </ul>
            </div>
          </div>
        ) : (
          <div>
            <Row>
              <Stat label="Inspected Candidate" value={inspected ? `MMSI ${inspected.mmsi} (${inspected.name || 'unnamed'})` : 'No candidate selected'} />
              <Stat label="Mean Speed" value={trajectory?.stats?.meanReportedSogKn != null ? fmtSpeed(trajectory.stats.meanReportedSogKn) : '—'} />
              <Stat label="Kinematic Loitering" value={trajectory?.stats ? `${fmtInt(trajectory.stats.stopPeriodCount)} stop / ${fmtInt(trajectory.stats.slowPeriodCount)} slow periods` : '—'} />
              <Stat label="Transponder Gaps" value={trajectory?.stats ? `${fmtInt(trajectory.stats.gapCount)} identified` : '—'} />
            </Row>

            <div style={{ marginTop: '16px' }}>
              <KeyValueTable
                rows={[
                  { key: 'Vessel Classification', value: inspected?.vesselType ? `${inspected.vesselType}` : '—' },
                  { key: 'Behaviour Anomaly', value: behaviour?.rawAnomaly != null ? `${fmtNumber(behaviour.rawAnomaly, 4)} (${behaviour.description || 'no description'})` : '—' },
                  { key: 'Anomaly Scored', value: behaviour?.scoredEligible === true ? `Yes — scored ${fmtNumber(behaviour.scoredAnomaly, 4)}` : 'No (context only)' },
                  { key: 'Gap Evidence', value: gapAnalysis?.hasGap ? `${fmtInt(gapAnalysis.gapCount)} gap(s), best value ${fmtNumber(gapAnalysis.bestEvidenceValue, 3)}` : 'No AIS gap in the track' },
                  { key: 'Inside Region During Window', value: compat?.insideRegionDuringWindow === true ? 'Yes' : compat?.insideRegionDuringWindow === false ? 'No' : '—' },
                ]}
              />
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
            Vessel kinematics indicate whether a ship was engaged in normal navigational transit or suspicious operations
            (e.g., deliberate AIS deactivation, loitering, speed reductions indicative of bilge or tank washing discharges).
          </p>
        </div>
      </Card>

      <div className="stage-actions" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <button type="button" className="btn btn-ghost" onClick={onPrevious}>
          ← PREVIOUS
        </button>
        <button type="button" className="btn btn-primary" onClick={onContinue}>
          CONTINUE TO EVIDENCE FUSION →
        </button>
      </div>
    </div>
  )
}
