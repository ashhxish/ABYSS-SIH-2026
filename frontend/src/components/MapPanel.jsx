import {
  boundsOf,
  graticule,
  lineToPath,
  makeProjector,
  niceScaleKm,
  pointsToPath,
  ringToLatLon,
  ringToPath,
} from '../lib/geo.js'
import { fmtLatitude, fmtLongitude, fmtNumber } from '../lib/format.js'
import { Card, Empty, NoticeList } from './ui.jsx'

const W = 860
const H = 520

/**
 * Schematic plot of the incident: observed slick, reconstructed origin region,
 * backdrift path and the selected vessel's AIS track.
 *
 * Drawn with plain SVG and a local equirectangular projection so the console
 * needs no map tiles, no API key and no network access. It is a sketch, not
 * navigation - the caption says so.
 */
export default function MapPanel({ investigation, detection, trajectories, trajectory, selected, onClearSelection }) {
  const slickRing = detection?.characterisation?.geometry
  const originRegion = investigation?.origin?.region
  const backdrift = investigation?.origin?.drift?.backdriftPath
  const candidateTracks = Array.isArray(trajectories?.trajectories) ? trajectories.trajectories : []
  const focus = [
    ...ringToLatLon(slickRing?.coordinates?.[0]),
    ...ringToLatLon(originRegion?.geometry?.coordinates?.[0]),
  ]
  const bounds = boundsOf(focus, 0.25)
  const projector = bounds ? makeProjector(bounds, W, H, 46) : null
  const ticks = graticule(bounds, 4)

  if (!projector) {
    return (
      <Card id="map" title="Incident plot" icon="🗺️">
        <Empty>No geometry available to plot yet.</Empty>
      </Card>
    )
  }

  const slickPath = slickRing ? ringToPath(slickRing.coordinates?.[0], projector) : ''
  const regionPath = originRegion?.geometry ? ringToPath(originRegion.geometry.coordinates[0], projector) : ''
  const driftPath = pointsToPath(backdrift, projector)
  const candidatePaths = candidateTracks
    .filter((candidate) => String(candidate.mmsi) !== String(trajectory?.mmsi))
    .map((candidate) => ({ mmsi: candidate.mmsi, name: candidate.vesselName, path: lineToPath(candidate.geometry?.coordinates, projector) }))
    .filter((candidate) => candidate.path)
  const trackPath = lineToPath(trajectory?.geometry?.coordinates, projector)
  const scaleKm = niceScaleKm(projector.kmPerPixel)
  const scalePx = scaleKm / projector.kmPerPixel
  const slickCentroid = detection?.characterisation?.centroid
  const centroidXY = slickCentroid ? projector.project(slickCentroid.lat, slickCentroid.lon) : null
  const driftStart = Array.isArray(backdrift) && backdrift.length ? backdrift[0] : null
  const driftStartXY = driftStart ? projector.project(driftStart[0], driftStart[1]) : null
  const originXY = originRegion?.geometry?.coordinates?.[0]?.[0]
    ? projector.project(originRegion.geometry.coordinates[0][0][1], originRegion.geometry.coordinates[0][0][0])
    : null
  const slickXY = centroidXY || (slickPath ? null : null)

  return (
    <Card
      subtitle="Observed slick, probable origin region, backdrift path and candidate AIS tracks"
      id="map"
      title="Incident plot"
      icon="🗺️"
      actions={selected ? <button className="btn btn-ghost" onClick={onClearSelection}>Clear track</button> : null}
    >
      <div className="map-wrap">
        <svg viewBox={`0 0 ${W} ${H}`} className="map-svg" role="img" aria-label="Schematic observed and modelled incident plot with candidate AIS tracks">
          <defs>
            <pattern id="sea" width="34" height="34" patternUnits="userSpaceOnUse">
              <rect width="34" height="34" fill="var(--map-bg)" />
              <path d="M0 34 L34 0" stroke="var(--map-grid)" strokeWidth="0.6" opacity="0.35" />
            </pattern>
            <filter id="glow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="5" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          <rect x="0" y="0" width={W} height={H} fill="url(#sea)" />
          {ticks.lats.map((lat) => {
            const [, y] = projector.project(lat, bounds.minLon)
            return <g key={`lat-${lat}`}><line x1="0" y1={y} x2={W} y2={y} stroke="var(--map-grid)" strokeWidth="0.7" /><text x="8" y={y - 4} className="map-tick">{fmtLatitude(lat, 2)}</text></g>
          })}
          {ticks.lons.map((lon) => {
            const [x] = projector.project(bounds.minLat, lon)
            return <g key={`lon-${lon}`}><line x1={x} y1="0" x2={x} y2={H} stroke="var(--map-grid)" strokeWidth="0.7" /><text x={x + 4} y={H - 8} className="map-tick">{fmtLongitude(lon, 2)}</text></g>
          })}

          {candidatePaths.map((candidate) => (
            <path key={candidate.mmsi} d={candidate.path} className="shape-candidate-track">
              <title>{`${candidate.name || 'Candidate'} · MMSI ${candidate.mmsi}`}</title>
            </path>
          ))}
          {regionPath ? <path d={regionPath} className="shape-region" filter="url(#glow)" /> : null}
          {slickPath ? <path d={slickPath} className="shape-slick" /> : null}
          {driftPath ? <path d={driftPath} className="shape-drift" /> : null}
          {trackPath ? <><path d={trackPath} className="shape-track-halo" /><path d={trackPath} className="shape-track"><title>{`${trajectory.vesselName || 'Selected vessel'} · MMSI ${trajectory.mmsi}`}</title></path></> : null}

          {driftStartXY ? <circle cx={driftStartXY[0]} cy={driftStartXY[1]} r="5" className="dot-drift" /> : null}
          {centroidXY ? <circle cx={centroidXY[0]} cy={centroidXY[1]} r="4" className="dot-slick" /> : null}
          {slickXY ? <text x={slickXY[0] + 8} y={slickXY[1] - 8} className="map-annotation" fill="var(--danger)">OBSERVED · SLICK</text> : null}
          {originXY ? <text x={originXY[0] + 8} y={originXY[1] - 8} className="map-annotation" fill="var(--ok)">MODELLED · ORIGIN REGION</text> : null}
          {trackPath ? <text x={W - 220} y={H - 52} className="map-annotation" fill="var(--accent)">SELECTED AIS TRACK</text> : null}

          <g transform={`translate(${W - scalePx - 40}, ${H - 34})`}>
            <line x1="0" y1="0" x2={scalePx} y2="0" stroke="var(--text-dim)" strokeWidth="2" />
            <line x1="0" y1="-5" x2="0" y2="5" stroke="var(--text-dim)" strokeWidth="2" />
            <line x1={scalePx} y1="-5" x2={scalePx} y2="5" stroke="var(--text-dim)" strokeWidth="2" />
            <text x={scalePx / 2} y="-8" textAnchor="middle" className="map-tick">{`${fmtNumber(scaleKm, scaleKm < 1 ? 1 : 0)} km`}</text>
          </g>
          <g transform={`translate(${W - 30}, 34)`}>
            <path d="M0 -16 L7 10 L0 4 L-7 10 Z" className="north-arrow" />
            <text x="0" y="24" textAnchor="middle" className="map-tick">N</text>
          </g>
        </svg>
      </div>

      <div className="map-legend" aria-label="Map evidence legend">
        <div className="legend-group"><strong>Observed evidence</strong><span><i className="key key-slick key-area" /> Oil slick</span><span><i className="key key-track" /> Selected AIS track</span><span className="legend-note">Direct scene/track observations</span></div>
        <div className="legend-group"><strong>Inferred / modelled</strong><span><i className="key key-region key-area" /> Uncertainty region</span><span><i className="key key-drift" /> Hindcast path</span><span className="legend-note">Analytical reconstruction</span></div>
        <div className="legend-group"><strong>Candidate context</strong><span><i className="key key-candidates" /> Other candidate tracks</span><span className="legend-note">AIS gaps are contextual, not proof.</span></div>
      </div>

      {trajectory ? (
        <NoticeList tone="info" title={`Selected AIS track: ${trajectory.vesselName || trajectory.mmsi}`} items={[
          `${trajectory.stats?.recordCount ?? 0} positions, ${fmtNumber(trajectory.stats?.observedDistanceKm, 1)} km observed`,
          `${trajectory.stats?.gapCount ?? 0} AIS gaps, ${trajectory.stats?.stopPeriodCount ?? 0} stop periods`,
          'The track is observed context; gaps are not evidence of wrongdoing on their own.',
        ]} />
      ) : <Empty>Select a candidate below to emphasize its reconstructed AIS track.</Empty>}
      <p className="fine-print">Schematic equirectangular plot without a basemap; not for navigation.</p>
    </Card>
  )
}
