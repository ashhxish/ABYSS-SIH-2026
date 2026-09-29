import { Badge, Bar, Card, Empty, NoticeList, Row } from './ui.jsx'

/**
 * Shared forensic-console presentation helpers. Every row carries its API
 * provenance; nothing here computes numbers — that all lives in lib/forensics.js.
 */

/** One provenance line, in the same `Source:` convention as the evidence chain. */
export function Provenance({ source, detail }) {
  if (!source) return null
  return (
    <p className="fine-print mono" title="API field this statement was derived from">
      Source: {source}
      {detail ? <span className="muted"> · {detail}</span> : null}
    </p>
  )
}

/** A ✓/⚠ line naming one supporting or caution item. */
export function EvidencePoint({ marker, tone, point }) {
  if (!point || !point.label) return null
  return (
    <li className="reason-list">
      <span className={tone === 'warn' ? 'warn-text' : undefined}>{marker}</span>{' '}
      {point.label}
      {point.detail ? <span className="muted"> — {point.detail}</span> : null}
      <br />
      <span className="fine-print mono">Source: {point.source || '—'}</span>
    </li>
  )
}

/** Compact labeled bar used by the sufficiency grid and comparison axes. */
export function MeterRow({ label, percent01, display, tone = 'accent', source, unavailable = false }) {
  return (
    <div className="factor-row">
      <div className="factor-head">
        <strong>{label}</strong>
        <span className="mono">{display}</span>
      </div>
      <div className="factor-bar">
        {unavailable ? null : <div className="factor-fill" style={{ width: `${(percent01 * 100).toFixed(1)}%` }} />}
      </div>
      <Provenance source={source} />
      {unavailable ? <Bar percent={0} tone="empty" label="Not available" /> : null}
    </div>
  )
}

/** Section heading shared by the forensic console panels. */
export function SectionHead({ children }) {
  return <h3 className="sub-head">{children}</h3>
}
