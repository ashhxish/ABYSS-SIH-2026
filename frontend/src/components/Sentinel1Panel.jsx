import { useState } from 'react'
import { Card, Row, Stat, Badge, Spinner } from './ui.jsx'
import { fmtNumber, fmtLatLon } from '../lib/format.js'
import { geoToFraction } from '../lib/geo.js'
import { matchedPositions, sceneBoundsOf } from '../lib/realais.js'

/**
 * Real AIS markers to overlay on the SAR preview.
 *
 * Only positions the AIS service actually returned for this scene are plotted,
 * placed with `geoToFraction` against the scene's own geographic bounds. A
 * single matched report yields a single marker - never a track.
 */
function aisOverlay(realAis, s1Data) {
  const bounds = sceneBoundsOf(s1Data)
  const positions = matchedPositions(realAis)
  const markers = []
  for (const position of positions) {
    const fraction = geoToFraction(position.lat, position.lon, bounds)
    if (fraction && fraction.inside) markers.push({ ...position, ...fraction })
  }
  return {
    bounds,
    markers,
    // A track is drawn only when 2+ real matched positions came back.
    track: markers.length >= 2 ? markers : null,
    // Matched positions that fall outside the footprint are reported, not plotted.
    outside: positions.length - markers.length,
  }
}

/**
 * Sentinel1Panel — Real Sentinel-1 SAR & U-Net Oil Spill Investigation Panel.
 *
 * Renders:
 *  - Real SAR previews (VV grayscale, VH grayscale, and composite false-color)
 *  - Actual U-Net predicted oil slick segmentation mask overlay (toggleable)
 *  - Real scene dimensions, bands, CRS, and geodesic area
 *  - Prominent real-data provenance (source file, model architecture, hashes)
 *  - Explicit missing acquisition time disclosure
 *  - Investigative limitation notice regarding candidate attribution vs. detection
 */
export default function Sentinel1Panel({ data, loading, error, onRetry, realAis }) {
  const [bandView, setBandView] = useState('vv') // 'vv' | 'vh' | 'composite'
  const [showMask, setShowMask] = useState(true)
  const [showAis, setShowAis] = useState(true)

  if (loading) {
    return (
      <Card id="sentinel1-investigation" title="REAL SENTINEL-1 INVESTIGATION" icon="🛰️">
        <div style={{ padding: '36px', textAlign: 'center' }}>
          <Spinner label="Executing PyTorch U-Net inference on 00999.tif (2048×2048, 64 patches)..." />
        </div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card id="sentinel1-investigation" title="REAL SENTINEL-1 INVESTIGATION" icon="🛰️">
        <div className="callout callout-danger" style={{ padding: '16px' }}>
          <h4>Inference Error</h4>
          <p className="error-text">{error}</p>
          <button className="btn" onClick={onRetry} style={{ marginTop: '12px' }}>Retry Inference</button>
        </div>
      </Card>
    )
  }

  if (!data) return null

  const obs = data.observation || {}
  const res = data.result || {}
  const char = obs.characteristics || {}
  const previews = data.previews || {}
  const prov = obs.provenance || {}
  const warnings = data.warnings || []

  const currentPreviewSrc =
    bandView === 'vh'
      ? previews.vh
      : bandView === 'composite'
      ? previews.composite
      : previews.vv

  // Real AIS matched positions, placed with the scene's own geographic bounds.
  const ais = aisOverlay(realAis, data)
  // The raster's own EPSG:4326 extent — also the box used to select AIS positions.
  const realSceneBounds = ais.bounds ?? sceneBoundsOf(data)

  return (
    <div className="sentinel1-container" style={{ display: 'grid', gap: '20px' }}>
      {/* Investigation Title and Status Banner */}
      <div
        className="s1-banner"
        style={{
          background: 'linear-gradient(135deg, rgba(14, 45, 74, 0.95), rgba(7, 24, 42, 0.95))',
          border: '1px solid var(--accent)',
          borderRadius: 'var(--radius)',
          padding: '16px 20px',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '12px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '20px' }}>🛰️</span>
            <h2 style={{ fontSize: '18px', color: 'var(--text)' }}>REAL SENTINEL-1 INVESTIGATION</h2>
            <Badge tone="ok">REAL SAR INGESTION</Badge>
            <Badge tone="accent">U-NET SEGMENTATION</Badge>
          </div>
          <p className="card-sub" style={{ margin: '4px 0 0 30px' }}>
            Direct neural segmentation of Sentinel-1 C-band Synthetic Aperture Radar imagery
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <button className="btn" onClick={onRetry}>
            Re-run Real Pipeline
          </button>
        </div>
      </div>

      {/* Prominent Limitation Warning */}
      <div
        className="s1-limitation"
        style={{
          background: 'rgba(251, 191, 36, 0.08)',
          borderLeft: '4px solid var(--warn)',
          borderRadius: 'var(--radius-sm)',
          padding: '12px 18px',
        }}
      >
        <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-dim)', lineHeight: 1.5 }}>
          <strong style={{ color: 'var(--warn)' }}>FORENSIC NOTICE: </strong>
          Sentinel-1 detection is based on the supplied SAR scene and trained U-Net model.
          This view does not yet establish vessel responsibility. AIS correlation and environmental
          drift analysis are separate forensic stages.
        </p>
      </div>

      {/* Main Grid: Left = SAR + U-Net Mask Viewer, Right = Statistics & Provenance */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '20px' }}>
        {/* Left Card: SAR Imagery & Mask Overlay */}
        <Card
          id="s1-viewer"
          title="SAR Scene & U-Net Slick Mask Overlay"
          subtitle="Direct pixel representation of 00999.tif with U-Net predicted oil slick"
          icon="🖼️"
          actions={
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <button
                type="button"
                className={`btn ${showAis ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setShowAis(!showAis)}
                style={{ fontSize: '12px', padding: '4px 10px' }}
                title="Real AIS matched positions only. No track is drawn unless the service returned two or more matched reports."
              >
                {showAis ? 'Hide AIS Positions' : 'Show AIS Positions'}
              </button>
              <button
                type="button"
                className={`btn ${showMask ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setShowMask(!showMask)}
                style={{ fontSize: '12px', padding: '4px 10px' }}
              >
                {showMask ? 'Hide Oil Mask' : 'Show Oil Mask'}
              </button>
            </div>
          }
        >
          {/* Layer toggles */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '14px', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>SAR Channel:</span>
            <button
              type="button"
              className={`btn ${bandView === 'vv' ? 'btn-primary' : 'btn-ghost'}`}
              style={{ fontSize: '12px', padding: '3px 9px' }}
              onClick={() => setBandView('vv')}
            >
              VV (Copolarized)
            </button>
            <button
              type="button"
              className={`btn ${bandView === 'vh' ? 'btn-primary' : 'btn-ghost'}`}
              style={{ fontSize: '12px', padding: '3px 9px' }}
              onClick={() => setBandView('vh')}
            >
              VH (Crosspolarized)
            </button>
            <button
              type="button"
              className={`btn ${bandView === 'composite' ? 'btn-primary' : 'btn-ghost'}`}
              style={{ fontSize: '12px', padding: '3px 9px' }}
              onClick={() => setBandView('composite')}
            >
              VV/VH Composite
            </button>
          </div>

          {/* Image & Overlay Stage */}
          <div
            style={{
              position: 'relative',
              width: '100%',
              aspectRatio: '1 / 1',
              background: '#040911',
              border: '1px solid var(--border-soft)',
              borderRadius: 'var(--radius-sm)',
              overflow: 'hidden',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {currentPreviewSrc ? (
              <img
                src={currentPreviewSrc}
                alt={`Sentinel-1 SAR ${bandView} band preview`}
                style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
              />
            ) : (
              <p className="muted">SAR preview unavailable</p>
            )}

            {showMask && previews.mask && (
              <img
                src={previews.mask}
                alt="U-Net Oil Spill Segmentation Mask Overlay"
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: '100%',
                  objectFit: 'contain',
                  pointerEvents: 'none',
                }}
              />
            )}

            {/* Real AIS matched positions, geopositioned on the SAR raster.
                The scene is an axis-aligned EPSG:4326 grid, so a fractional
                lon/lat mapping is exact (verified against rasterio). */}
            {showAis && ais.markers.length > 0 && (
              <svg
                viewBox="0 0 1 1"
                preserveAspectRatio="none"
                aria-label="Real AIS matched positions over the SAR preview"
                role="img"
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: '100%',
                  pointerEvents: 'none',
                }}
              >
                {ais.track ? (
                  <polyline
                    points={ais.track.map((m) => `${m.x},${m.y}`).join(' ')}
                    fill="none"
                    stroke="rgba(52, 211, 153, 0.9)"
                    strokeWidth={0.004}
                    strokeDasharray="0.012 0.008"
                  />
                ) : null}
                {ais.markers.map((marker) => (
                  <g key={`${marker.mmsi ?? 'unknown'}-${marker.lat}-${marker.lon}`}>
                    <circle
                      cx={marker.x}
                      cy={marker.y}
                      r={0.03}
                      fill="none"
                      stroke="rgba(52, 211, 153, 0.55)"
                      strokeWidth={0.004}
                    />
                    <circle cx={marker.x} cy={marker.y} r={0.011} fill="#34d399" />
                    <line
                      x1={marker.x - 0.045}
                      y1={marker.y}
                      x2={marker.x + 0.045}
                      y2={marker.y}
                      stroke="rgba(52, 211, 153, 0.85)"
                      strokeWidth={0.003}
                    />
                    <line
                      x1={marker.x}
                      y1={marker.y - 0.045}
                      x2={marker.x}
                      y2={marker.y + 0.045}
                      stroke="rgba(52, 211, 153, 0.85)"
                      strokeWidth={0.003}
                    />
                    <text
                      x={marker.x + 0.05}
                      y={marker.y - 0.03}
                      fontSize={0.028}
                      fill="#34d399"
                      style={{ fontWeight: 600 }}
                    >
                      {`REAL AIS · MMSI ${marker.mmsi ?? '—'}`}
                    </text>
                  </g>
                ))}
              </svg>
            )}
          </div>

          {/* What the overlay means - spatial only, never temporal */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '14px', alignItems: 'center', marginTop: '10px', fontSize: '11.5px', color: 'var(--text-dim)' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <i style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#34d399', display: 'inline-block' }} />
              Real AIS matched position{ais.markers.length === 1 ? '' : 's'} ({ais.markers.length}) · spatial match only
            </span>
            <span>
              {previews.mask ? 'Red/derived overlay: U-Net predicted slick mask' : 'Slick mask unavailable'}
            </span>
          </div>
          {ais.outside > 0 ? (
            <p className="fine-print" style={{ marginTop: '6px' }}>
              {ais.outside} matched report{ais.outside === 1 ? '' : 's'} fell outside the displayed
              raster extent and {ais.outside === 1 ? 'is' : 'are'} not drawn.
            </p>
          ) : null}
          {realAis ? (
            <p className="fine-print" style={{ marginTop: '6px' }}>
              AIS positions come from the real NOAA/OAR/PMEL extract via{' '}
              <span className="mono">POST /ais/real/analyze</span>. TEMPORAL MATCH: UNAVAILABLE —
              the Sentinel-1 acquisition timestamp is unknown, so this marker is a spatial
              coincidence in time-agnostic terms and is not an attribution.
            </p>
          ) : null}

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-dim)' }}>
              Layer: <strong style={{ color: 'var(--text)' }}>{bandView.toUpperCase()}</strong>
              {showMask ? ' + Predicted Slick (Red Highlight)' : ' (Mask Hidden)'}
            </span>
            <span className="mono" style={{ fontSize: '11.5px', color: 'var(--text-mute)' }}>
              2048 × 2048 px · EPSG:4326
            </span>
          </div>
        </Card>

        {/* Right Card: Real Computed Detection Statistics */}
        <Card
          id="s1-stats"
          title="Computed Detection Statistics"
          subtitle="Physical properties and neural inference metrics"
          icon="📊"
        >
          <div className="stat-row" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px', marginBottom: '16px' }}>
            <Stat
              label="Detected Slick Area"
              value={`${fmtNumber(res.areaKm2 ?? char.areaKm2, 3)} km²`}
              sub="Geodesic authalic area"
              tone="accent"
            />
            <Stat
              label="Oil Pixels"
              value={fmtNumber(res.oilPixels ?? char.oilPixels, 0)}
              sub={`Fraction: ${fmtNumber((res.oilFraction ?? char.oilFraction ?? 0) * 100, 3)}%`}
              tone="neutral"
            />
            <Stat
              label="Connected Regions"
              value={fmtNumber(res.regions ? res.regions.length : char.regionCount, 0)}
              sub="Components ≥ 5 px"
              tone="neutral"
            />
            <Stat
              label="U-Net Threshold"
              value="0.50"
              sub="Sigmoid probability cut"
              tone="ok"
            />
          </div>

          <div style={{ display: 'grid', gap: '8px' }}>
            <Row label="Image Dimensions" value={`${char.sceneWidth ?? 2048} × ${char.sceneHeight ?? 2048} px`} mono />
            <Row label="SAR Polarization" value="VV + VH (Dual Pol)" mono />
            <Row label="Coordinate System (CRS)" value={char.crs ?? 'EPSG:4326 (WGS 84)'} mono />
            <Row
              label="Centroid Coordinates"
              value={res.centroid ? fmtLatLon(res.centroid.lat, res.centroid.lon, 4) : '—'}
              mono
            />
            <Row
              label="Bounding Box"
              value={
                realSceneBounds
                  ? `[${realSceneBounds.map((v) => fmtNumber(v, 4)).join(', ')}]`
                  : '—'
              }
              hint="west, south, east, north (EPSG:4326) — the same box used to select AIS positions"
              mono
            />
            <Row
              label="Detection Confidence"
              value="Not calibrated (Binary Mask)"
              hint="The U-Net model generates a binary segmentation mask, not calibrated posterior confidence"
            />
          </div>
        </Card>
      </div>

      {/* Provenance & Audit Card */}
      <Card
        id="s1-provenance"
        title="Provenance & Forensic Audit Trail"
        subtitle="Verification parameters and metadata disclosures"
        icon="🛡️"
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '20px' }}>
          <div>
            <h3 style={{ fontSize: '13px', color: 'var(--text-dim)', marginBottom: '8px' }}>SOURCE SCENE SPECIFICATION</h3>
            <div style={{ display: 'grid', gap: '6px' }}>
              <Row label="Source File" value={prov.sourceFile || '00999.tif'} mono />
              <Row label="Sensor Platform" value="Sentinel-1 SAR (C-Band)" />
              <Row label="Input Channels" value="VV, VH Float32" mono />
              <Row
                label="Acquisition Timestamp"
                value="Unavailable in source metadata"
                hint="processed_at is not an acquisition time and was rejected"
              />
            </div>
          </div>

          <div>
            <h3 style={{ fontSize: '13px', color: 'var(--text-dim)', marginBottom: '8px' }}>NEURAL MODEL SPECIFICATION</h3>
            <div style={{ display: 'grid', gap: '6px' }}>
              <Row label="Model Architecture" value="U-Net (DoubleConv, Bilinear Up)" />
              <Row label="Weights Checkpoint" value="best_unet_oil_spill.pth" mono />
              <Row label="Model SHA-256" value={(char.modelSha256 || '90fb25fd...').slice(0, 16) + '...'} mono />
              <Row label="Patch Strategy" value="256 × 256 non-overlapping (64 patches)" mono />
              <Row label="Preprocessing" value="Per-channel patch standardisation (mean/std)" />
            </div>
          </div>
        </div>

        {/* Warnings / Disclosures */}
        {warnings && warnings.length > 0 && (
          <div style={{ marginTop: '16px' }}>
            <h3 style={{ fontSize: '13px', color: 'var(--warn)', marginBottom: '6px' }}>METADATA DISCLOSURES & AUDIT WARNINGS</h3>
            <ul style={{ margin: 0, paddingLeft: '18px', color: 'var(--text-dim)', fontSize: '12.5px' }}>
              {warnings.map((w, idx) => (
                <li key={idx} style={{ marginBottom: '4px' }}>{w}</li>
              ))}
            </ul>
          </div>
        )}
      </Card>
    </div>
  )
}
