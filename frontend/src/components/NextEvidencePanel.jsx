import { Badge, Card, Empty, NoticeList } from './ui.jsx'
import { EvidencePoint, SectionHead } from './forensicShared.jsx'

/**
 * Features 6 + 7 — Investigation status and recommended next evidence.
 *
 * Feature 6: a reusable status state. When evidence is weak the panel says
 * INSUFFICIENT EVIDENCE with only reasons the data supports, plus the
 * recommended next evidence to close the gaps. When evidence is adequate
 * (as for the CASE-001 lead) it says so — the insufficient state is never
 * forced.
 *
 * Feature 7: decision support, not autonomous decision-making. Each
 * recommendation fires only on the missing/weak evidence that justifies it.
 */
export default function NextEvidencePanel({ status, next }) {
  if (!status) {
    return (
      <Card id="investigation-status" title="Investigation status" subtitle="Evidence adequacy for the selected candidate" icon="🧭">
        <Empty>Status is unavailable until an investigation response loads.</Empty>
      </Card>
    )
  }

  return (
    <Card
      id="investigation-status"
      title="Investigation status"
      subtitle={status.candidate ? `Selected candidate vessel · ${status.candidate.name}${status.candidate.rank != null ? ` · rank ${status.candidate.rank}` : ''}` : 'Selected candidate vessel'}
      icon="🧭"
      actions={<Badge tone={status.tone}>{status.state}</Badge>}
    >
      <p className="fine-print"><strong>{status.headline}</strong></p>
      <p className="fine-print">
        Evidence sufficiency: <strong>{status.sufficiencyStatus}</strong>{' '}
        at a composite of <span className="mono">{status.compositeDisplay}</span>.{' '}
        {status.standing}
      </p>

      {status.insufficient ? (
        <>
          <SectionHead>Why this candidate cannot be prioritised yet</SectionHead>
          {status.reasons.length === 0 ? (
            <p className="fine-print">No reason was recorded — treat the ordering as an agenda for review.</p>
          ) : (
            <ul className="reason-list" style={{ listStyle: 'none', paddingLeft: 0 }}>
              {status.reasons.map((reason, i) => (
                <EvidencePoint key={i} marker="•" point={reason} />
              ))}
            </ul>
          )}
        </>
      ) : null}

      <SectionHead>Recommended next evidence</SectionHead>
      {!next || next.empty ? (
        <p className="fine-print">{next?.message || 'No missing or weak evidence was identified in this API response.'}</p>
      ) : (
        <>
          <p className="fine-print">{next.message}</p>
          {next.highPriority > 0 ? (
            <p className="fine-print"><Badge tone="warn">{next.highPriority} high priority</Badge></p>
          ) : null}
          <div className="factor-list">
            {next.recommendations.map((rec) => (
              <div className="factor-row" key={rec.id}>
                <div className="factor-head">
                  <strong>{rec.title}</strong>
                  <Badge tone={rec.priority === 'high' ? 'warn' : 'neutral'}>{rec.priority}</Badge>
                </div>
                <p className="fine-print">{rec.why}</p>
                <p className="fine-print">
                  Addresses: {rec.addresses}{' '}
                  <span className="mono">Source: {rec.source}</span>
                </p>
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  )
}
