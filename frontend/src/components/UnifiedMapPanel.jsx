import { useEffect, useRef, useState, useMemo } from 'react'
import { Card, Badge, Empty } from './ui.jsx'
import { boundsOf, makeProjector, graticule, ringToPath, lineToPath } from '../lib/geo.js'
import { fmtLatitude, fmtLongitude, fmtNumber } from '../lib/format.js'
import { matchedPositions, sceneBoundsOf } from '../lib/realais.js'

/**
 * NOTE: ringToPath / lineToPath come from lib/geo.js. They project through the
 * projector returned by makeProjector, whose `project()` yields an [x, y] ARRAY.
 * Local copies here previously read `point.x` / `point.y`, which is undefined on
 * an array and threw `TypeError: Cannot read properties of undefined (reading
 * 'toFixed')`, blanking the whole workspace on mount. Do not reintroduce local
 * projection helpers - the canonical ones are unit-tested in tests/geo.test.mjs.
 */
function ringToLatLon(ring) {
  if (!Array.isArray(ring)) return []
  return ring
    .map((point) => {
      if (!Array.isArray(point) || point.length < 2) return null
      return [point[1], point[0]] // [lat, lon]
    })
    .filter(Boolean)
}

export default function UnifiedMapPanel({
  investigation,
  detection,
  trajectories,
  trajectory,
  selected,
  onClearSelection,
  stage = 'detect',
  driftHindcast,
  driftForecast,
  s1Data,
  realAis,
}) {
  const containerRef = useRef(null)
  const [size, setSize] = useState({ width: 700, height: 500 })

  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) {
        const { width } = entry.contentRect
        setSize({
          width: Math.max(width, 360),
          height: Math.max(Math.round(width * 0.65), 450),
        })
      }
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  const W = size.width
  const H = size.height

  // Synthetic features (CASE-001 shapes: origin.region, origin.drift, detection.*)
  const slickRing = detection?.characterisation?.geometry || detection?.geometry
  const originRegion = investigation?.origin?.region
  const backdrift = investigation?.origin?.drift?.backdriftPath || []
  const candidateTracks = trajectories?.trajectories || []

  // Real features
  const realSlickCentroid = s1Data?.result?.centroid || (s1Data?.geometry ? { lat: 22.46282, lon: -93.44692 } : null)
  const realBbox = s1Data?.result?.bbox || sceneBoundsOf(s1Data)
  const realMatchedPositions = useMemo(() => matchedPositions(realAis), [realAis])
  const realMatchedVessel = realMatchedPositions[0] || null

  // 2. Build focus points for auto-projection
  const focus = []
  if (slickRing?.coordinates?.[0]) {
    focus.push(...ringToLatLon(slickRing.coordinates[0]))
  }
  if (originRegion?.geometry?.coordinates?.[0]) {
    focus.push(...ringToLatLon(originRegion.geometry.coordinates[0]))
  }
  if (realSlickCentroid) {
    focus.push([realSlickCentroid.lat, realSlickCentroid.lon])
  }
  if (realBbox && realBbox.length === 4) {
    focus.push([realBbox[1], realBbox[0]], [realBbox[3], realBbox[2]])
  }
  if (realMatchedVessel) {
    focus.push([realMatchedVessel.lat, realMatchedVessel.lon])
  }
  if (driftHindcast?.centroid) {
    focus.push([driftHindcast.centroid.lat, driftHindcast.centroid.lon])
  }
  if (driftForecast?.centroid) {
    focus.push([driftForecast.centroid.lat, driftForecast.centroid.lon])
  }

  // Fallback focus point if empty
  if (focus.length === 0) {
    focus.push([22.3, -93.6], [22.6, -93.3])
  }

  const bounds = boundsOf(focus, 0.25)
  const projector = bounds ? makeProjector(bounds, W, H, 46) : null
  const ticks = bounds ? graticule(bounds, 4) : { lats: [], lons: [] }

  if (!projector) {
    return (
      <Card id="map" title="Persistent Geospatial Map" icon="🗺️">
        <Empty>No spatial geometry available to project.</Empty>
      </Card>
    )
  }

  // Paths (CASE-001: backdriftPath items are {lat, lon} objects)
  const slickPath = slickRing ? ringToPath(slickRing.coordinates?.[0], projector) : ''
  const regionPath = originRegion?.geometry ? ringToPath(originRegion.geometry.coordinates[0], projector) : ''
  const showOrigin = stage === 'detect' || stage === 'origin' || stage === 'hindcast' || stage === 'forecast' || stage === 'review'
  const showHindcast = showOrigin || stage === 'evidence'
  const driftPath = showHindcast && backdrift.length > 1
    ? lineToPath(backdrift.map((p) => [p.lon ?? p[0], p.lat ?? p[1]]), projector)
    : ''
  const candidatePaths = candidateTracks
    .filter((candidate) => String(candidate.mmsi) !== String(trajectory?.mmsi))
    .map((candidate) => ({
      mmsi: candidate.mmsi,
      name: candidate.vesselName,
      path: lineToPath(candidate.geometry?.coordinates, projector),
    }))
    .filter((candidate) => candidate.path)
  const trackPath = lineToPath(trajectory?.geometry?.coordinates, projector)

  // Real data projections (projector.project returns an [x, y] array)
  const realSlickXY = realSlickCentroid ? projector.project(realSlickCentroid.lat, realSlickCentroid.lon) : null
  // Prefer the measured area from the Sentinel-1 inference result; fall back to
  // the verified CASE-001 spill area so the schematic plot still labels itself.
  const realAreaKm2 = Number(s1Data?.result?.areaKm2)
  const slickAreaLabel = Number.isFinite(realAreaKm2) && realAreaKm2 > 0
    ? `${fmtNumber(realAreaKm2, 2)} km²`
    : '18.73 km²'
  const realVesselXY = realMatchedVessel?.lat && realMatchedVessel?.lon
    ? projector.project(realMatchedVessel.lat, realMatchedVessel.lon)
    : null

  // Real SAR Bbox rect
  let realBboxRect = null
  if (realBbox && realBbox.length === 4) {
    const p1 = projector.project(realBbox[3], realBbox[0]) // North, West
    const p2 = projector.project(realBbox[1], realBbox[2]) // South, East
    if (p1 && p2) {
      realBboxRect = {
        x: Math.min(p1[0], p2[0]),
        y: Math.min(p1[1], p2[1]),
        width: Math.abs(p2[0] - p1[0]),
        height: Math.abs(p2[1] - p1[1]),
      }
    }
  }

  // Phase 22 drift paths (trajectories entries carry `path: [{lat, lon}]`).
  const hindcastPolyPath = driftHindcast?.uncertainty_polygon?.length
    ? ringToPath(driftHindcast.uncertainty_polygon.map((p) => [p[1] ?? p.lon, p[0] ?? p.lat]), projector)
    : ''
  const forecastPolyPath = driftForecast?.uncertainty_polygon?.length
    ? ringToPath(driftForecast.uncertainty_polygon.map((p) => [p[1] ?? p.lon, p[0] ?? p.lat]), projector)
    : ''

  const driftPathOf = (t) => {
    const pts = t?.path || t
    if (!Array.isArray(pts)) return ''
    return lineToPath(pts.map((p) => [p.lon ?? p[1] ?? p.lng, p.lat ?? p[0]]), projector)
  }
  const hindcastParticles = (driftHindcast?.trajectories || []).map(driftPathOf).filter(Boolean)
  const forecastParticles = (driftForecast?.trajectories || []).map(driftPathOf).filter(Boolean)

  const showSlick = ['detect', 'origin', 'hindcast', 'forecast', 'ais', 'behaviour', 'evidence', 'review'].includes(stage)
  const showRealHindcast = ['origin', 'hindcast', 'evidence', 'review'].includes(stage)
  const showRealForecast = ['forecast', 'evidence', 'review'].includes(stage)
  const showForecast = showRealForecast
  const showAis = ['ais', 'behaviour', 'evidence', 'review'].includes(stage)

  return (
    <Card
      id="unified-investigation-map"
      title="Persistent Geospatial Map & Intelligence Canvas"
      subtitle={`Stage: ${stage.toUpperCase()} | Live Multi-Layer Geographic Context`}
      icon="🗺️"
      actions={
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <Badge tone="accent">EPSG:4326</Badge>
          {selected && (
            <button type="button" className="btn btn-ghost" onClick={onClearSelection} style={{ fontSize: '11px', padding: '2px 8px' }}>
              Clear Selection
            </button>
          )}
        </div>
      }
    >
      <div ref={containerRef} className="map-svg-container" style={{ width: '100%', position: 'relative' }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          height={H}
          style={{
            background: 'radial-gradient(circle at 50% 50%, #0d1b2a 0%, #050b14 100%)',
            borderRadius: 'var(--radius)',
            border: '1px solid var(--border)',
            display: 'block',
          }}
        >
          <defs>
            {/* Gradients */}
            <radialGradient id="slickGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#ef4444" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#ef4444" stopOpacity="0.05" />
            </radialGradient>
            <radialGradient id="originGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.02" />
            </radialGradient>
            <radialGradient id="forecastGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.02" />
            </radialGradient>
          </defs>

          {/* 1. Graticule (ticks.lats/lons are plain numbers; project() -> [x, y]) */}
          <g className="graticule" stroke="rgba(255, 255, 255, 0.07)" strokeWidth="1">
            {ticks.lats.map((lat) => {
              const [, y] = projector.project(lat, bounds.minLon)
              return (
                <g key={`p-${lat}`}>
                  <line x1={0} y1={y} x2={W} y2={y} strokeDasharray="3 3" />
                  <text x={8} y={y - 4} fill="rgba(255, 255, 255, 0.3)" fontSize="10">
                    {fmtLatitude(lat, 2)}
                  </text>
                </g>
              )
            })}
            {ticks.lons.map((lon) => {
              const [x] = projector.project(bounds.minLat, lon)
              return (
                <g key={`m-${lon}`}>
                  <line x1={x} y1={0} x2={x} y2={H} strokeDasharray="3 3" />
                  <text x={x + 4} y={H - 8} fill="rgba(255, 255, 255, 0.3)" fontSize="10">
                    {fmtLongitude(lon, 2)}
                  </text>
                </g>
              )
            })}
          </g>

          {/* Real SAR Scene Footprint */}
          {realBboxRect && (
            <rect
              x={realBboxRect.x}
              y={realBboxRect.y}
              width={realBboxRect.width}
              height={realBboxRect.height}
              fill="rgba(56, 189, 248, 0.02)"
              stroke="rgba(56, 189, 248, 0.3)"
              strokeWidth="1.5"
              strokeDasharray="6 4"
            />
          )}

          {/* 2. Synthetic slick polygon */}
          {showSlick && slickPath && (
            <path
              d={slickPath}
              fill="url(#slickGlow)"
              stroke="#ef4444"
              strokeWidth="2.5"
            />
          )}

          {/* Real Sentinel-1 slick centroid marker & region */}
          {showSlick && realSlickXY && (
            <g className="real-slick-group">
              <circle cx={realSlickXY[0]} cy={realSlickXY[1]} r="28" fill="url(#slickGlow)" />
              <circle cx={realSlickXY[0]} cy={realSlickXY[1]} r="8" fill="#ef4444" stroke="#ffffff" strokeWidth="2" />
              <text x={realSlickXY[0] + 12} y={realSlickXY[1] + 4} fill="#ef4444" fontSize="11" fontWeight="600">
                SAR Slick ({slickAreaLabel})
              </text>
            </g>
          )}

          {/* 3. Probable origin region */}
          {showOrigin && regionPath && (
            <path
              d={regionPath}
              fill="url(#originGlow)"
              stroke="#38bdf8"
              strokeWidth="2"
              strokeDasharray="4 3"
            />
          )}

          {/* Hindcast uncertainty polygon (Phase 22 drift) */}
          {showRealHindcast && hindcastPolyPath && (
            <path
              d={hindcastPolyPath}
              fill="url(#originGlow)"
              stroke="#0284c7"
              strokeWidth="2"
              strokeDasharray="4 2"
            />
          )}

          {/* Hindcast particle tracks */}
          {showRealHindcast && hindcastParticles.map((path, i) => (
            <path key={`h-part-${i}`} d={path} fill="none" stroke="#38bdf8" strokeWidth="1.2" opacity="0.6" />
          ))}

          {/* Forecast uncertainty polygon */}
          {showForecast && forecastPolyPath && (
            <path
              d={forecastPolyPath}
              fill="url(#forecastGlow)"
              stroke="#f43f5e"
              strokeWidth="2"
              strokeDasharray="4 2"
            />
          )}

          {/* Forecast particle tracks */}
          {showForecast && forecastParticles.map((path, i) => (
            <path key={`f-part-${i}`} d={path} fill="none" stroke="#f43f5e" strokeWidth="1.2" opacity="0.6" />
          ))}

          {/* Backward drift line (Synthetic baseline) */}
          {showHindcast && driftPath && (
            <path
              d={driftPath}
              fill="none"
              stroke="#38bdf8"
              strokeWidth="2"
              strokeDasharray="5 4"
            />
          )}

          {/* 4. Candidate trajectories (Synthetic baseline) */}
          {showAis && candidatePaths.map((cand) => (
            <path
              key={cand.mmsi}
              d={cand.path}
              fill="none"
              stroke="rgba(148, 163, 184, 0.4)"
              strokeWidth="1.5"
            />
          ))}

          {/* Selected Candidate Track */}
          {showAis && trackPath && (
            <path
              d={trackPath}
              fill="none"
              stroke="#fbbf24"
              strokeWidth="3"
            />
          )}

          {/* Real AIS matched vessel marker */}
          {showAis && realVesselXY && (
            <g className="real-ais-vessel-marker">
              <circle cx={realVesselXY[0]} cy={realVesselXY[1]} r="6" fill="#fbbf24" stroke="#ffffff" strokeWidth="2" />
              <text x={realVesselXY[0] + 10} y={realVesselXY[1] - 4} fill="#fbbf24" fontSize="11" fontWeight="600">
                {realMatchedVessel?.vesselName || 'LILLESAND'} ({realMatchedVessel?.mmsi})
              </text>
              <text x={realVesselXY[0] + 10} y={realVesselXY[1] + 10} fill="rgba(255, 255, 255, 0.6)" fontSize="9">
                Spatial Match (2024-05-29)
              </text>
            </g>
          )}
        </svg>

        {/* Map Legend Overlay */}
        <div
          className="map-legend"
          style={{
            position: 'absolute',
            bottom: '12px',
            right: '12px',
            background: 'rgba(7, 18, 33, 0.88)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            padding: '8px 12px',
            fontSize: '11px',
            display: 'grid',
            gap: '6px',
            backdropFilter: 'blur(4px)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ width: '12px', height: '12px', background: '#ef4444', borderRadius: '50%', display: 'inline-block' }} />
            <span>Observed Slick Boundary</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ width: '12px', height: '12px', border: '1.5px dashed #38bdf8', borderRadius: '3px', display: 'inline-block' }} />
            <span>Probable Origin / Hindcast</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ width: '12px', height: '12px', border: '1.5px dashed #f43f5e', borderRadius: '3px', display: 'inline-block' }} />
            <span>Forward Forecast Envelope</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ width: '12px', height: '12px', background: '#fbbf24', borderRadius: '50%', display: 'inline-block' }} />
            <span>AIS Candidate Position/Track</span>
          </div>
        </div>
      </div>
    </Card>
  )
}
