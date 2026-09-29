import { Card, Row, Stat, Badge, NoticeList, Spinner, Empty } from './ui.jsx'
import { fmtInt, fmtNumber, fmtUtcSeconds, fmtLatitude, fmtLongitude } from '../lib/format.js'
import { geoToFraction } from '../lib/geo.js'
import {
  TEMPORAL_LIMITATION_TEXT,
  realAisCounts,
  matchedVessels,
  aisBoxMatchesScene,
  sceneBoundsOf,
} from '../lib/realais.js'

/**
 * RealAisPanel — REAL AIS TRAFFIC for the real Sentinel-1 investigation.
 *
 * Shows the real NOAA/OAR/PMEL AIS extract and the vessels whose positions fall
 * inside the real Sentinel-1 scene footprint, straight from
 * `POST /ais/real/analyze`.
 *
 * Forensic limits enforced by construction:
 *  - No synthetic AIS, no synthetic-demo candidate values, no scores and no
 *    causation wording: this view renders only counts, identifiers,
 *    coordinates and timestamps that the service returned.
 *  - The extract-wide vessel count is never conflated with the scene match: the
 *    two are labelled "AIS DATASET" and "SPATIAL MATCH" and shown separately.
 *  - When the service cannot be reached the panel says so and substitutes
 *    nothing.
 */

export default function RealAisPanel({ data, loading, error, onRetry, s1Data }) {
  const sceneBounds = sceneBoundsOf(s1Data)

  if (loading) {
    return (
      <Card id="real-ais" title="REAL AIS TRAFFIC" icon="🚢">
        <div style={{ padding: '30px', textAlign: 'center' }}>
          <Spinner label="Loading the real NOAA AIS extract and selecting positions inside the Sentinel-1 scene footprint…" />
        </div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card
        id="real-ais"
        title="REAL AIS TRAFFIC"
        subtitle="NOAA/OAR/PMEL real AIS extract selected against the Sentinel-1 scene footprint"
        icon="🚢"
      >
        <div
          className="notice notice-warn"
          style={{ borderColor: 'rgba(251, 113, 133, 0.4)', background: 'rgba(251, 113, 133, 0.07)' }}
        >
          <strong style={{ color: 'var(--danger)' }}>REAL AIS SERVICE UNAVAILABLE</strong>
          <p className="error-text" style={{ margin: '6px 0' }}>{error}</p>
          <p style={{ margin: 0, color: 'var(--text-dim)', fontSize: '12px' }}>
            No AIS data is shown for this scene. Synthetic AIS data is deliberately
            <strong> not</strong> substituted, so this section stays empty until the
            service answers.
          </p>
        </div>
        <button className="btn" onClick={onRetry} style={{ marginTop: '12px' }}>
          Retry real AIS analysis
        </button>
      </Card>
    )
  }

  if (!data) return null

  const counts = realAisCounts(data)
  const vessels = matchedVessels(data)
  const boxIsScene = aisBoxMatchesScene(data, s1Data)
  const warnings = Array.isArray(data.warnings) ? data.warnings : []
  const spatialNote = data.analysis?.spatial?.note ?? null

  return (
    <Card
      id="real-ais"
      title="REAL AIS TRAFFIC"
      subtitle="NOAA/OAR/PMEL real AIS extract selected against the Sentinel-1 scene footprint"
      icon="🚢"
      actions={
        <button className="btn btn-ghost" onClick={onRetry}>
          Refresh real AIS
        </button>
      }
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '14px' }}>
        <Badge tone="ok">REAL AIS · NOAA/OAR/PMEL</Badge>
        <Badge tone="accent">SPATIAL SELECTION ONLY</Badge>
        <Badge tone="warn">TEMPORAL MATCH: UNAVAILABLE</Badge>
      </div>

      {/* Source provenance, verbatim from the service */}
      <div style={{ display: 'grid', gap: '6px', marginBottom: '18px' }}>
        <Row label="Source" value={data.source?.provider ?? data.dataSource ?? '—'} mono />
        <Row label="Extract" value={data.source?.uri ?? '—'} mono />
        <Row
          label="Synthetic"
          value={data.realAis === true && data.source?.synthetic === false ? 'No (real extract)' : 'Unknown'}
          hint="The real-AIS path never returns synthetic records"
        />
        <Row label="Service label" value={data.label ?? '—'} mono />
      </div>

      {/* Dataset vs scene-match: two SEPARATE groups, never merged */}
      <h3 style={{ fontSize: '13px', color: 'var(--text-dim)', marginBottom: '8px' }}>
        AIS DATASET — FULL EXTRACT
      </h3>
      <div
        className="stat-row"
        style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '12px', marginBottom: '18px' }}
      >
        <Stat label="AIS records loaded" value={fmtInt(counts.raw)} tone="accent" />
        <Stat label="Accepted" value={fmtInt(counts.accepted)} tone="ok" />
        <Stat label="Rejected" value={fmtInt(counts.rejected)} tone="warn" />
        <Stat label="Warnings" value={fmtInt(counts.warnings)} />
        <Stat label="Unique vessels loaded" value={fmtInt(counts.vesselsLoaded)} />
        <Stat label="Reconstructed trajectories" value={fmtInt(counts.trajectories)} />
        <Stat label="AIS transmission gaps" value={fmtInt(counts.gaps)} />
      </div>

      <h3 style={{ fontSize: '13px', color: 'var(--text-dim)', marginBottom: '8px' }}>
        SPATIAL MATCH — INSIDE THE SENTINEL-1 SCENE FOOTPRINT
      </h3>
      <div className="stat-row" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '12px' }}>
        <Stat
          label="Spatially matched vessels"
          value={fmtInt(counts.matchedVessels)}
          sub="Of the loaded AIS dataset"
          tone={counts.matchedVessels ? 'accent' : 'neutral'}
        />
        <Stat
          label="Spatially matched positions"
          value={fmtInt(counts.matchedPositions)}
          sub="Real AIS reports inside the box"
          tone={counts.matchedPositions ? 'accent' : 'neutral'}
        />
      </div>

      <NoticeList
        tone="info"
        title="Reading these two groups"
        items={[
          `The extract contains ${fmtInt(counts.vesselsLoaded)} unique vessels; ${fmtInt(counts.matchedVessels)} of them have a position inside the Sentinel-1 scene footprint.`,
          'The dataset total describes the whole NOAA extract, which extends well beyond this scene. It is not a count of vessels in the scene.',
        ]}
      />

      <div style={{ display: 'grid', gap: '6px', marginTop: '16px' }}>
        <Row
          label="Spatial selection box"
          value={Array.isArray(data.spatialBBox) ? `[${data.spatialBBox.map((v) => fmtNumber(v, 5)).join(', ')}]` : '—'}
          mono
          hint="west, south, east, north in EPSG:4326"
        />
        <Row
          label="Scene box from the SAR raster"
          value={sceneBounds ? `[${sceneBounds.map((v) => fmtNumber(v, 5)).join(', ')}]` : 'Unavailable'}
          mono
        />
        <Row
          label="Selection equals the displayed SAR scene"
          value={boxIsScene === null ? 'Not verified' : boxIsScene ? 'Yes' : 'No'}
          hint="Cross-check of the AIS selection box against the Sentinel-1 scene bounds"
        />
      </div>

      {/* Matched vessels */}
      <h3 style={{ fontSize: '13px', color: 'var(--text-dim)', margin: '20px 0 8px' }}>
        SPATIALLY MATCHED VESSEL{counts.matchedVessels === 1 ? '' : 'S'}
      </h3>

      {vessels.length === 0 ? (
        <Empty>
          0 spatially matched vessels — no real AIS report falls inside the Sentinel-1
          scene footprint. No vessel was fabricated to fill this section.
        </Empty>
      ) : (
        <div style={{ display: 'grid', gap: '14px' }}>
          {vessels.map((vessel) => {
            const matchedLat = vessel.matchedFirstPosition?.latitude
            const matchedLon = vessel.matchedFirstPosition?.longitude
            const firstPoint = geoToFraction(vessel.firstPosition?.latitude, vessel.firstPosition?.longitude, sceneBounds)
            const lastPoint = geoToFraction(vessel.lastPosition?.latitude, vessel.lastPosition?.longitude, sceneBounds)
            const extractWideIsOutside =
              firstPoint && lastPoint && !firstPoint.inside && !lastPoint.inside
            return (
              <div
                key={String(vessel.mmsi)}
                style={{
                  border: '1px solid var(--border-soft)',
                  borderLeft: '4px solid var(--accent)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '12px 16px',
                }}
              >
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                  <strong style={{ fontSize: '15px', color: 'var(--text)' }}>
                    {vessel.vesselName || 'Unnamed vessel'}
                  </strong>
                  <Badge tone="ok">SPATIAL MATCH · REAL AIS</Badge>
                  <Badge tone="neutral">NO TEMPORAL MATCH</Badge>
                </div>

                <div style={{ display: 'grid', gap: '6px' }}>
                  <Row label="MMSI" value={vessel.mmsi ?? '—'} mono />
                  <Row label="IMO" value={vessel.imo ?? '—'} mono />
                  <Row label="Vessel type" value={vessel.vesselType === null ? '—' : String(vessel.vesselType)} mono />
                  <Row label="Matched reports" value={fmtInt(vessel.matchedPointCount)} />
                  <Row
                    label="Timestamp"
                    value={fmtUtcSeconds(vessel.matchedStartTimestamp)}
                    mono
                    hint="Raw AIS report time, reproduced from the service response"
                  />
                  <Row label="Latitude" value={fmtLatitude(matchedLat)} mono />
                  <Row label="Longitude" value={fmtLongitude(matchedLon)} mono />
                </div>

                <h4 style={{ fontSize: '12px', color: 'var(--text-dim)', margin: '12px 0 6px' }}>
                  EXTRACT-WIDE TRAJECTORY CONTEXT
                </h4>
                <div style={{ display: 'grid', gap: '6px' }}>
                  <Row label="Reports in trajectory" value={fmtInt(vessel.pointCount)} />
                  <Row
                    label="Trajectory span"
                    value={`${fmtUtcSeconds(vessel.startTimestamp)} → ${fmtUtcSeconds(vessel.endTimestamp)}`}
                    mono
                  />
                  <Row
                    label="First position (extract)"
                    value={
                      vessel.firstPosition
                        ? `${fmtLatitude(vessel.firstPosition.latitude)}, ${fmtLongitude(vessel.firstPosition.longitude)}`
                        : '—'
                    }
                    mono
                  />
                  <Row
                    label="Last position (extract)"
                    value={
                      vessel.lastPosition
                        ? `${fmtLatitude(vessel.lastPosition.latitude)}, ${fmtLongitude(vessel.lastPosition.longitude)}`
                        : '—'
                    }
                    mono
                  />
                  <Row label="AIS gaps in trajectory" value={fmtInt(vessel.gapCount)} />
                </div>
                {extractWideIsOutside ? (
                  <p className="fine-print" style={{ marginTop: '8px' }}>
                    The extract-wide trajectory lies outside the Sentinel-1 footprint, so it is
                    shown as context only and is not plotted on the SAR scene.
                  </p>
                ) : null}
                {vessel.matchedPointCount === 1 ? (
                  <p className="fine-print" style={{ marginTop: '8px' }}>
                    Exactly one matched report: no track is drawn for this vessel, only the single
                    real position.
                  </p>
                ) : null}
              </div>
            )
          })}
        </div>
      )}

      {/* The forensic limitation, kept prominent */}
      <div
        style={{
          marginTop: '18px',
          background: 'rgba(251, 191, 36, 0.08)',
          borderLeft: '4px solid var(--warn)',
          borderRadius: 'var(--radius-sm)',
          padding: '12px 18px',
        }}
      >
        <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-dim)', lineHeight: 1.55 }}>
          <strong style={{ color: 'var(--warn)' }}>TEMPORAL MATCH: UNAVAILABLE — </strong>
          {data.temporalMatchReason || 'Sentinel-1 acquisition timestamp unavailable.'}
        </p>
        <p style={{ margin: '8px 0 0', fontSize: '13px', color: 'var(--text-dim)', lineHeight: 1.55 }}>
          {TEMPORAL_LIMITATION_TEXT}
        </p>
        <p style={{ margin: '8px 0 0', fontSize: '12px', color: 'var(--text-mute)' }}>
          No responsibility score, ranking or cause is computed for this real scene. The service
          reports <span className="mono">temporalMatchAvailable = {String(data.temporalMatchAvailable)}</span>.
        </p>
      </div>

      {spatialNote ? (
        <NoticeList tone="warn" title="Service note on this selection" items={[spatialNote]} />
      ) : null}

      {warnings.length > 0 ? (
        <details style={{ marginTop: '12px' }}>
          <summary style={{ cursor: 'pointer', fontSize: '12px', color: 'var(--text-dim)' }}>
            {fmtInt(warnings.length)} ingest warning{warnings.length === 1 ? '' : 's'} (first few)
          </summary>
          <ul style={{ margin: '8px 0 0', paddingLeft: '18px', color: 'var(--text-dim)', fontSize: '12px' }}>
            {warnings.slice(0, 5).map((warning, index) => (
              <li key={index} style={{ marginBottom: '4px' }} className="mono">{warning}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <p className="fine-print" style={{ marginTop: '12px' }}>
        Real AIS extract: NOAA/OAR/PMEL. Positions are plotted only where the service returned a
        matched report; the console invents no AIS data.
      </p>
    </Card>
  )
}
