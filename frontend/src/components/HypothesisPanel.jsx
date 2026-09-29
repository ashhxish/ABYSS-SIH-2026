import { Badge, Card, Empty, NoticeList } from './ui.jsx'
import { EvidencePoint, SectionHead } from './forensicShared.jsx'

/**
 * Feature 3 — Competing hypotheses.
 *
 * ABYSS must show it does not force one answer: the candidate-vessel
 * hypothesis sits beside the alternatives the data can and cannot evaluate.
 * Statuses come verbatim from `competingHypotheses`; no hypothesis carries a
 * numeric probability because the system publishes no calibrated one.
 */
function HypothesisCard({ hypothesis }) {
  const list = (items, marker, tone) => (
    items.length === 0 ? (
      <p className="fine-print">None identified in the available data.</p>
    ) : (
      <ul className="reason-list" style={{ listStyle: 'none', paddingLeft: 0 }}>
        {items.map((point, i) => (
          typeof point === 'string'
            ? <li key={i} className="reason-list"><span className={tone === 'warn' ? 'warn-text' : undefined}>{marker}</span> {point}</li>
            : <EvidencePoint key={i} marker={marker} tone={tone} point={point} />
        ))}
      </ul>
    )
  )

  return (
    <div className="factor-row">
      <div className="factor-head">
        <strong>{hypothesis.title}</strong>
        <Badge tone={hypothesis.tone}>{hypothesis.status}</Badge>
      </div>
      <p className="fine-print">{hypothesis.statement}</p>
      <p className="fine-print">{hypothesis.explanation}</p>
      <div className="detail-columns">
        <div>
          <SectionHead>Supporting evidence</SectionHead>
          {list(hypothesis.supporting, '✓')}
        </div>
        <div>
          <SectionHead>Contradicting evidence</SectionHead>
          {list(hypothesis.contradicting, '✕', 'warn')}
        </div>
      </div>
      <SectionHead>Uncertainty</SectionHead>
      {list(hypothesis.uncertainty, '⚠', 'warn')}
      <p className="fine-print">
        No numeric probability is attached: the system publishes no calibrated probability.{' '}
        {hypothesis.sources.length > 0 ? (
          <span className="mono">Sources: {hypothesis.sources.join(', ')}</span>
        ) : (
          <span className="mono">Sources: none integrated for this hypothesis</span>
        )}
      </p>
    </div>
  )
}

export default function HypothesisPanel({ result }) {
  if (!result || !Array.isArray(result.hypotheses)) {
    return (
      <Card id="alternative-hypotheses" title="Alternative hypotheses" subtitle="What else could explain the observed event" icon="🔀">
        <Empty>Hypotheses are unavailable until an investigation response loads.</Empty>
      </Card>
    )
  }

  return (
    <Card
      id="alternative-hypotheses"
      title="Alternative hypotheses"
      subtitle="ABYSS does not force one answer — each alternative is weighed on the same evidence"
      icon="🔀"
    >
      <p className="fine-print">{result.note}</p>
      <div className="factor-list">
        {result.hypotheses.map((h) => <HypothesisCard key={h.id} hypothesis={h} />)}
      </div>
    </Card>
  )
}
