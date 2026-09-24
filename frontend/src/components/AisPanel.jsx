import { fmtInt, fmtKm, fmtNumber } from '../lib/format.js'
import { Badge, Card, Empty, NoticeList, Row, Spinner, Stat } from './ui.jsx'

/**
 * Step 4: AIS handling - cleaning audit, trajectory reconstruction totals and
 * the screening filters applied to every vessel. Data from /ais/clean and
 * /ais/trajectory (loaded lazily because the bundle is ~2 MB).
 */
export default function AisPanel({ cleaning, trajectories, loading, error, onRetry }) {
  const counts = trajectories?.statistics?.counts || cleaning?.statistics?.counts || {}
  const cleanCounts = cleaning?.statistics?.counts || {}
  const totals = trajectories?.statistics?.totals || {}

  return (
    <Card
      id="ais"
      title="AIS processing & screening"
      subtitle="Cleaning audit, reconstructed trajectories and origin-region filters"
      icon="🚢"
      actions={
        loading ? <Spinner label="Loading trajectories" /> : (
          <Badge tone="ok">{fmtInt(counts.vessels)} vessels reconstructed</Badge>
        )
      }
    >
      {error ? (
        <div className="error-block">
          <p className="error-text">{error}</p>
          <button className="btn" onClick={onRetry}>Retry AIS data</button>
        </div>
      ) : null}

      <div className="stat-row">
        <Stat label="Raw reports" value={fmtInt(cleanCounts.records ?? counts.records)} sub={`${fmtInt(cleanCounts.rowsIn)} rows ingested`} />
        <Stat label="Rejected rows" value={fmtInt(cleanCounts.rowsRejected)} sub="duplicate / implausible" />
        <Stat label="Vessels" value={fmtInt(counts.vessels)} sub="with reconstructed tracks" />
        <Stat label="Segments" value={fmtInt(counts.segments)} sub="consecutive position pairs" />
        <Stat label="Gaps" value={fmtInt(counts.gaps)} sub={`${fmtInt(counts.vesselsWithGaps)} vessels affected`} />
        <Stat label="Stop periods" value={fmtInt(counts.stopPeriods)} sub="sustained low-speed periods" />
      </div>

      {trajectories ? (
        <div className="detail-columns">
          <div>
            <h3 className="sub-head">Track totals</h3>
            <Row label="Observed distance" value={fmtKm(totals.observedDistanceKm, 1)} />
            <Row label="Straight-line gap distance" value={fmtKm(totals.straightLineGapKm, 1)} />
            <Row label="Course changes" value={fmtInt(counts.courseChanges)} sub={`${fmtInt(counts.vesselsWithCourseChanges)} vessels`} />
            <Row label="Slow periods" value={fmtInt(counts.slowPeriods)} />
            <Row label="Missing speed reports" value={fmtInt(counts.recordsWithMissingSpeed)} />
            <Row label="Skipped records" value={fmtInt(trajectories.skippedRecords ?? counts.skippedRecords)} />
          </div>
          <div>
            <h3 className="sub-head">Screening configuration</h3>
            <Row label="Max plausible speed" value={`${fmtNumber(trajectories.config?.maxPlausibleSpeedKn, 1)} kn`} />
            <Row label="Gap threshold" value={`${fmtNumber(trajectories.config?.gapThresholdSeconds, 0)} s`} />
            <Row label="Source" value={trajectories.source?.provider || trajectories.dataSource || 'DemoAISProvider'} />
            <Row label="Dataset" value={(trajectories.source?.datasetLabels || []).join(', ') || trajectories.datasetLabel || '—'} />
            <NoticeList tone="info" title="Trajectory notes" items={trajectories.notes} />
          </div>
        </div>
      ) : (
        !error && <Empty>{loading ? 'Loading reconstructed trajectories…' : 'Trajectory bundle not loaded.'}</Empty>
      )}

      <NoticeList title="AIS warnings" items={(trajectories?.warnings || []).concat(cleaning?.warnings || [])} />
    </Card>
  )
}
