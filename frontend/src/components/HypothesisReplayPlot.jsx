import { Badge, Card, Empty } from './ui.jsx'
import { Provenance, SectionHead } from './forensicShared.jsx'
import { boundsOf, makeProjector, lineToPath, ringToPath, pointsToPath, graticule } from '../lib/geo.js'
import { fmtLatitude, fmtLongitude } from '../lib/format.js'

/**
 * Feature 5 — Hypothesis Replay (part 1: the schematic plot).
 *
 * Built ONLY from geometry lib/forensics.js already normalised
 * (`replay.geo`): candidate track, probable origin region, modelled
 * backward drift, observed slick and — when supplied — the forward
 * footprint. Projection reuses the tested lib/geo.js helpers (the same
 * ones UnifiedMapPanel uses), so no local projection code can drift.
 *
 * The plot is schematic, labelled as such, and answers “could this
 * candidate’s recorded movement be consistent with the observed event?” —
 * never “this proves the vessel caused the spill.”
 */

const PLOT_W = 640
const PLOT_H = 420

/** [{lat, lon}] -> [[lon, lat]] ring for the GeoJSON helpers in lib/geo.js. */
function toRing(points) {
  if (!Array.isArray(points) || points.length < 3) return null
  return points.map((p) => [p.lon, p.lat])
}

function PlotDot({ projector, point }) {
  if (!point) return null
  const [x, y] = projector.project(point.lat, point.lon)
  return <circle cx={x} cy={y} r={4} className="dot-drift" />
}

export function ReplayPlot({ geo }) {
  const forwardExtra = [...(geo.forwardPolygon || []), ...(geo.forwardPaths || []).flat()]
  const bounds = boundsOf([...geo.slick, ...geo.origin, ...geo.backdrift, ...geo.track, ...forwardExtra])
  if (!bounds) return <Empty>No replay geometry is available for this candidate.</Empty>
  const projector = makeProjector(bounds, PLOT_W, PLOT_H, 30)
  if (!projector) return <Empty>Replay geometry could not be framed.</Empty>
  const ticks = graticule(bounds, 3)

  const slickRing = toRing(geo.slick)
  const originRing = toRing(geo.origin)
  const forwardRing = toRing(geo.forwardPolygon || [])
  const driftPath = geo.backdrift.length >= 2 ? pointsToPath(geo.backdrift, projector) : ''
  const trackPath = geo.track.length >= 2 ? pointsToPath(geo.track, projector) : ''
  // Phase-22 forward tracks are already [{lat, lon}] points; the GeoJSON
  // helper expects [[lon, lat]] rings, so they convert before drawing.
  const forwardTrackPaths = (geo.forwardPaths || [])
    .map((points) => {
      const ring = Array.isArray(points) && points.length >= 2 ? points.map((p) => [p.lon, p.lat]) : null
      return ring ? lineToPath(ring, projector) : ''
    })
    .filter(Boolean)

  return (
    <div className="map-wrap">
      <svg className="map-svg" viewBox={`0 0 ${PLOT_W} ${PLOT_H}`} width="100%" role="img" aria-label="Hypothesis replay schematic plot">
        {ticks.lats.map((lat) => {
          const pos = projector.project(lat, bounds.minLon)
          const y = pos[1]
          return (
            <g key={`lat-${lat}`}>
              <line x1={0} y1={y} x2={PLOT_W} y2={y} stroke="rgba(255,255,255,0.07)" strokeWidth={1} />
              <text x={8} y={y - 4} className="map-tick">{fmtLatitude(lat, 2)}</text>
            </g>
          )
        })}
        {ticks.lons.map((lon) => {
          const pos = projector.project(bounds.minLat, lon)
          const x = pos[0]
          return (
            <g key={`lon-${lon}`}>
              <line x1={x} y1={0} x2={x} y2={PLOT_H} stroke="rgba(255,255,255,0.07)" strokeWidth={1} />
              <text x={x + 4} y={PLOT_H - 8} className="map-tick">{fmtLongitude(lon, 2)}</text>
            </g>
          )
        })}
        {forwardRing ? <path d={ringToPath(forwardRing, projector)} fill="rgba(244,63,94,0.10)" stroke="#f43f5e" strokeWidth={1.6} strokeDasharray="6 4" /> : null}
        {originRing ? <path d={ringToPath(originRing, projector)} className="shape-region" /> : null}
        {slickRing ? <path d={ringToPath(slickRing, projector)} className="shape-slick" /> : null}
        {trackPath ? <path d={trackPath} className="shape-track" /> : null}
        {driftPath ? <path d={driftPath} className="shape-drift" /> : null}
        {forwardTrackPaths.map((d, i) => (
          <path key={`fwd-${i}`} d={d} fill="none" stroke="#f43f5e" strokeWidth={1.6} strokeDasharray="3 5" opacity={0.9} />
        ))}
        <PlotDot projector={projector} point={geo.backdrift[0]} />
        <PlotDot projector={projector} point={geo.backdrift[geo.backdrift.length - 1]} />
        <PlotDot projector={projector} point={geo.track[0]} />
        <PlotDot projector={projector} point={geo.track[geo.track.length - 1]} />
      </svg>
    </div>
  )
}
