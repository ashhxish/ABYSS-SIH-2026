import { useMemo } from 'react'
import { fmtDateTime, fmtDuration } from '../lib/format.js'
import {
  EVIDENCE_STATUS,
  STATUS_MEANING,
  buildTimeline,
  countByStatus,
  isEmphasised,
  summariseTimeline,
  timelineRange,
} from '../lib/timeline.js'
import { Badge, Card, Empty } from './ui.jsx'

const STATUS_TONE = {
  OBSERVED: 'ok',
  PRIOR: 'info',
  MODELLED: 'accent',
  ANALYTICAL: 'neutral',
}

/** Duration between two API timestamps - subtracted, never invented. */
function spanLabel(event) {
  const start = Date.parse(event.at)
  const end = Date.parse(event.end)
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null
  return fmtDuration((end - start) / 1000)
}

function EventRow({ event, selected, onSelect }) {
  const emphasised = isEmphasised(event, selected)
  const dimmed = Boolean(selected) && !emphasised
  const span = event.end ? spanLabel(event) : null
  const clickable = event.scope === 'vessel' && typeof onSelect === 'function' && Boolean(event.mmsi)
  const classes = ['tl-item', `tl-${String(event.status).toLowerCase()}`]
  if (emphasised && event.scope === 'vessel') classes.push('tl-emph')
  if (dimmed) classes.push('tl-dim')
  if (clickable) classes.push('tl-clickable')

  return (
    <li
      className={classes.join(' ')}
      onClick={clickable ? () => onSelect(event.mmsi) : undefined}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={clickable ? (e) => e.key === 'Enter' && onSelect(event.mmsi) : undefined}
      title={clickable ? 'Show this vessel in the ranking and evidence panels' : undefined}
    >
      <div className="tl-when">
        <span className="tl-time mono">{event.at ? fmtDateTime(event.at) : 'time not recorded'}</span>
        {event.end ? <span className="tl-range mono">→ {fmtDateTime(event.end)}</span> : null}
        {span ? <span className="tl-span mono">{span}</span> : null}
      </div>
      <div className="tl-body">
        <div className="tl-head">
          <strong>{event.title}</strong>
          <span className="tl-chips">
            <Badge tone={STATUS_TONE[event.status] || 'neutral'} title={STATUS_MEANING[event.status]}>
              {event.status}
            </Badge>
            <Badge tone="neutral">{event.type}</Badge>
            {event.confidence != null ? (
              <Badge tone="accent">{Math.round(event.confidence * 100)}% confidence</Badge>
            ) : null}
          </span>
        </div>
        {event.description ? <p className="tl-desc">{event.description}</p> : null}
        {event.metrics.length > 0 ? (
          <dl className="tl-metrics">
            {event.metrics.map((metric) => (
              <div key={metric.label}>
                <dt>{metric.label}</dt>
                <dd className="mono">{metric.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        <span className="tl-source mono" title="API field this entry was read from">
          Source: {event.source}
        </span>
      </div>
    </li>
  )
}

/**
 * Phase 16 - chronological forensic timeline.
 *
 * Ordering, status and every displayed value come from the API payloads the
 * console already holds (see lib/timeline.js). Steps whose API payload carries
 * no timestamp are listed separately rather than given an invented time.
 */
export default function Timeline({ investigation, detection, selected, onSelect }) {
  const timeline = useMemo(() => buildTimeline(investigation, detection), [investigation, detection])
  const narrative = useMemo(() => summariseTimeline(investigation), [investigation])
  const range = timelineRange(timeline)
  const counts = countByStatus(timeline)
  const selectedEntry = useMemo(
    () => (investigation?.ranking?.entries || []).find((e) => String(e.mmsi) === String(selected)) || null,
    [investigation, selected],
  )

  if (!investigation) {
    return (
      <Card id="timeline" title="Investigation timeline" icon="🕒">
        <Empty>The timeline is built from the investigation response, which has not loaded.</Empty>
      </Card>
    )
  }

  return (
    <Card
      id="timeline"
      title="Investigation timeline"
      subtitle="Chronological evidence sequence — observed data, model output and analysis"
      icon="🕒"
      actions={
        <span className="muted">
          {timeline.timed.length} timed · {timeline.untimed.length} untimed
          {range.spanHours != null ? ` · ${range.spanHours} h span` : ''}
        </span>
      }
    >
      <div className="tl-legend">
        {Object.values(EVIDENCE_STATUS).map((status) => (
          <span className="tl-legend-item" key={status}>
            <Badge tone={STATUS_TONE[status]}>{status}</Badge>
            <span className="muted">{STATUS_MEANING[status]}</span>
            <span className="mono muted">{counts[status]}</span>
          </span>
        ))}
      </div>

      <section className="summary-block">
        <h3 className="sub-head">Investigation summary</h3>
        <ol className="summary-flow">
          {narrative.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ol>
        {selectedEntry ? (
          <p className="fine-print">
            Emphasised below: evidence recorded for{' '}
            <strong>{selectedEntry.name || `MMSI ${selectedEntry.mmsi}`}</strong> (rank {selectedEntry.rank},
            investigation priority {selectedEntry.totalScore?.toFixed(1) ?? '—'}). Other vessels remain visible as
            context.
          </p>
        ) : (
          <p className="fine-print">
            Showing the whole-case chronology. Select a candidate in the ranking to emphasise that vessel&apos;s own
            recorded evidence.
          </p>
        )}
      </section>

      {timeline.timed.length === 0 ? (
        <Empty>No timeline entry in this response carries a recorded timestamp.</Empty>
      ) : (
        <ol className="tl-track">
          {timeline.timed.map((event) => (
            <EventRow key={event.id} event={event} selected={selected} onSelect={onSelect} />
          ))}
        </ol>
      )}

      {timeline.untimed.length > 0 ? (
        <section className="tl-untimed">
          <h3 className="sub-head">Analysis steps without a recorded timestamp</h3>
          <p className="fine-print">
            These steps appear in the API response without a timestamp, so they are listed here instead of being placed
            at an invented time.
          </p>
          <ul className="tl-track tl-track-plain">
            {timeline.untimed.map((event) => (
              <EventRow key={event.id} event={event} selected={selected} onSelect={onSelect} />
            ))}
          </ul>
        </section>
      ) : null}
    </Card>
  )
}

