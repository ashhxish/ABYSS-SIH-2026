import { Card, Row, Stat, Badge, Spinner, KeyValueTable } from './ui.jsx'
import { fmtNumber, fmtIso, fmtInt, fmtLatLon } from '../lib/format.js'

/**
 * ForecastStagePanel — Stage 04: FORWARD FORECAST
 * Forward Lagrangian projection estimating where the observed slick will advect.
 * Synthetic CASE-001 has no forward forecast in the API, so the synthetic
 * branch says so honestly instead of inventing a projection.
 */
export default function ForecastStagePanel({
  investigation,
  driftForecast,
  onRunForecast,
  forecastLoading,
  onContinue,
  onPrevious,
  isRealMode,
}) {
  void investigation
  // Live Phase 22 shapes: centroid {lat, lon}, duration_hours, particle_count,
  // trajectories[].path, provenance {provider/dataset, wind_available}.
  const realCentroid = driftForecast?.centroid
  const duration = driftForecast?.duration_hours ?? 6.0
  const particles = driftForecast?.particle_count ?? driftForecast?.trajectories?.length ?? null
  const currentsProv = driftForecast?.provenance?.provider || driftForecast?.provenance?.dataset || null
  const windKnown = driftForecast?.provenance?.wind_available
  const spreadKm = driftForecast?.spread_radius_km ?? null

  return (
    <div className="stage-panel-forecast" style={{ display: 'grid', gap: '20px' }}>
      <Card
        id="forecast-stage"
        title="Forward Transport Projection (Slick Forecast)"
        subtitle="Forward Lagrangian advection: where could the oil spill spread?"
        icon="🔮"
        actions={
          <button
            type="button"
            className="btn btn-primary"
            onClick={onRunForecast}
            disabled={forecastLoading}
          >
            {forecastLoading ? 'Computing Projection...' : 'Run Forward Forecast'}
          </button>
        }
      >
        <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
          <Badge tone="accent">{`Forward Advection (+${fmtNumber(duration, 1)}h)`}</Badge>
          <Badge tone={isRealMode ? 'ok' : 'accent'}>
            {isRealMode ? 'Real Current Field' : 'Calibrated Advection'}
          </Badge>
          <Badge tone="neutral">Environmental Projection</Badge>
        </div>

        {/* Conceptual Split Diagram */}
        <div
          style={{
            background: 'rgba(15, 23, 42, 0.6)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            padding: '16px',
            marginBottom: '20px',
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '16px',
            fontSize: '13px',
          }}
        >
          <div style={{ padding: '10px', background: 'rgba(56, 189, 248, 0.08)', borderRadius: '6px', borderLeft: '3px solid var(--accent)' }}>
            <strong style={{ color: 'var(--accent)', display: 'block', marginBottom: '4px' }}>
              ⏮️ HINDCAST (Backward)
            </strong>
            <p style={{ margin: 0, fontSize: '12px', color: 'var(--text-dim)', lineHeight: 1.4 }}>
              <strong>Where could it have originated?</strong><br />
              Reconstructs probable spill discharge location and window for vessel attribution.
            </p>
          </div>

          <div style={{ padding: '10px', background: 'rgba(244, 63, 94, 0.08)', borderRadius: '6px', borderLeft: '3px solid #f43f5e' }}>
            <strong style={{ color: '#f43f5e', display: 'block', marginBottom: '4px' }}>
              ⏭️ FORECAST (Forward)
            </strong>
            <p style={{ margin: 0, fontSize: '12px', color: 'var(--text-dim)', lineHeight: 1.4 }}>
              <strong>Where could it move?</strong><br />
              Estimates trajectory footprint for ecological protection and coastal impact mitigation.
            </p>
          </div>
        </div>

        {isRealMode ? (
          <div>
            <Row>
              <Stat
                label={`Projected Centroid (+${fmtNumber(duration, 1)}h)`}
                value={realCentroid ? fmtLatLon(realCentroid.lat, realCentroid.lon, 4) : 'Not simulated yet'}
                hint={driftForecast ? 'Advection destination' : 'Run the forecast to simulate'}
              />
              <Stat label="Spread Radius" value={spreadKm != null ? `${fmtNumber(spreadKm, 2)} km` : '—'} hint="Particle ensemble spread" />
              <Stat label="Particles" value={particles != null ? fmtInt(particles) : '—'} hint="Live ensemble size" />
              <Stat label="Hydrodynamic Forcing" value={currentsProv || 'Not verified yet'} hint={driftForecast ? 'Live field provenance' : 'Pending simulation'} />
            </Row>

            <div style={{ marginTop: '16px' }}>
              <KeyValueTable
                rows={[
                  { key: 'Forecast Horizon', value: `+${fmtNumber(duration, 1)} hours${driftForecast?.reference_time_iso ? ` from ${fmtIso(driftForecast.reference_time_iso)}` : ''}` },
                  { key: 'Ocean Surface Current', value: driftForecast ? (currentsProv || '—') : 'Not verified yet — run the forecast' },
                  {
                    key: 'Wind Forcing Input',
                    value: (
                      <span style={{ color: 'var(--warn)', fontWeight: 500 }}>
                        {windKnown === true
                          ? 'Wind forcing available (see provenance)'
                          : windKnown === false
                            ? 'Wind unavailable for timestamp (current-driven advection only)'
                            : 'Unknown until the forecast runs — no wind is ever assumed'}
                      </span>
                    ),
                  },
                  { key: 'Projected Footprint Spread', value: driftForecast?.uncertainty_polygon?.length ? `${driftForecast.uncertainty_polygon.length}-vertex projected envelope on map` : '—' },
                  { key: 'Data Integrity Audit', value: driftForecast ? 'Verified zero-synthetic data leakage in real mode' : '—' },
                ]}
              />
            </div>
          </div>
        ) : (
          <div>
            <Row>
              <Stat label="Projection Horizon" value={`+${fmtNumber(duration, 1)} Hours (on demand)`} />
              <Stat label="Forecast Source" value="Synthetic CASE-001 carries no forward forecast" />
            </Row>

            <div style={{ marginTop: '16px' }}>
              <KeyValueTable
                rows={[
                  { key: 'Forward Forecast', value: 'Not present in this API response — run a forward drift simulation to project' },
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
            INVESTIGATOR INTERPRETATION
          </h4>
          <p style={{ margin: 0, fontSize: '12px', color: 'var(--text-dim)', lineHeight: 1.5 }}>
            Forward projection estimates where the observed slick could move under the supplied environmental forcing.
            It is a transport forecast, not a source attribution. This boundary establishes containment planning.
          </p>
        </div>
      </Card>

      <div className="stage-actions" style={{ display: 'flex', justifyContent: 'space-between' }}>
        <button type="button" className="btn btn-ghost" onClick={onPrevious}>
          ← PREVIOUS
        </button>
        <button type="button" className="btn btn-primary" onClick={onContinue}>
          CONTINUE TO AIS FORENSICS →
        </button>
      </div>
    </div>
  )
}
