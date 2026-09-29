import { Badge, Card, Empty, NoticeList } from './ui.jsx'
import { EvidencePoint, Provenance, SectionHead } from './forensicShared.jsx'
import { SUFFICIENCY_RANK } from '../lib/forensics.js'

/**
 * Feature 1 — Evidence Sufficiency Gate.
 *
 * Deterministic investigation-priority assessment for the selected candidate.
 * The band, composite and lists come verbatim from `assessEvidenceSufficiency`;
 * this panel only renders. Never a guilt verdict: the standing line says so.
 */
export default function EvidenceSufficiencyPanel({ assessment, name }) {
  if (!assessment || !assessment.available) {
    return (
      <Card id="evidence-sufficiency" title="Evidence sufficiency" subtitle="Selected candidate vessel" icon="⚖️">
        <Empty>Select a candidate vessel in the ranking to assess evidence sufficiency.</Empty>
      </Card>
    )
  }

  const gaugeFrac = assessment.composite == null ? 0 : assessment.composite / 100
  const gaugeCirc = 2 * Math.PI * 53
  const gaugeTone = assessment.tone === 'ok' ? 'var(--ok)' : assessment.tone === 'warn' ? 'var(--warn)' : 'var(--danger)'

  return (
    <Card
      id="evidence-sufficiency"
      title="Evidence sufficiency"
      subtitle={name ? `Selected candidate vessel · ${name}` : 'Selected candidate vessel'}
      icon="⚖️"
      actions={<Badge tone={assessment.tone}>{assessment.status}</Badge>}
    >
      <div className="confidence-grid">
        <div className="gauge-block">
          <div className="gauge">
            <svg width={120} height={120} viewBox="0 0 120 120" role="img" aria-label={`Evidence compatibility composite ${assessment.compositeDisplay}`}>
              <circle cx={60} cy={60} r={53} fill="none" stroke="var(--border)" strokeWidth={11} />
              <circle
                cx={60} cy={60} r={53} fill="none" stroke={gaugeTone} strokeWidth={11} strokeLinecap="round"
                strokeDasharray={`${(gaugeCirc * gaugeFrac).toFixed(2)} ${gaugeCirc.toFixed(2)}`}
                transform="rotate(-90 60 60)"
              />
              <text x="50%" y="47%" textAnchor="middle" className="gauge-value">
                {assessment.composite == null ? 'n/a' : `${assessment.composite}%`}
              </text>
              <text x="50%" y="63%" textAnchor="middle" className="gauge-caption">composite</text>
            </svg>
          </div>
        </div>
        <div className="fact-block">
          <p className="fine-print">{assessment.explanation}</p>
          <p className="fine-print">{assessment.standing}</p>
          {assessment.limiting ? (
            <p className="fine-print">
              Binding constraint: <strong>{assessment.limiting.label}</strong>{' '}
              <span className="mono">{assessment.limiting.detail}</span>{' '}
              <span className="mono">Source: {assessment.limiting.source}</span>
            </p>
          ) : null}
        </div>
      </div>

      <SectionHead>Dimension readings</SectionHead>
      <div className="factor-list">
        {assessment.dimensions.map((d) => (
          <div className="factor-row" key={d.key}>
            <div className="factor-head">
              <strong>{d.label}</strong>
              <span className="mono">{d.display}</span>
            </div>
            <div className="factor-bar">
              {d.available ? <div className="factor-fill" style={{ width: `${Math.max(0, Math.min(100, d.percent)).toFixed(1)}%` }} /> : null}
            </div>
            {d.detail ? <small>{d.detail}</small> : null}
            <Provenance source={d.source} />
          </div>
        ))}
      </div>

      <div className="detail-columns">
        <div>
          <SectionHead>Supporting</SectionHead>
          {assessment.supporting.length === 0 ? (
            <p className="fine-print">No dimension currently clears the supporting threshold.</p>
          ) : (
            <ul className="reason-list" style={{ listStyle: 'none', paddingLeft: 0 }}>
              {assessment.supporting.map((point, i) => (
                <EvidencePoint key={i} marker="✓" point={point} />
              ))}
            </ul>
          )}
        </div>
        <div>
          <SectionHead>Caution</SectionHead>
          {assessment.caution.length === 0 ? (
            <p className="fine-print">No caution raised by the available dimensions.</p>
          ) : (
            <ul className="reason-list" style={{ listStyle: 'none', paddingLeft: 0 }}>
              {assessment.caution.map((point, i) => (
                <EvidencePoint key={i} marker="⚠" tone="warn" point={point} />
              ))}
            </ul>
          )}
        </div>
      </div>

      <NoticeList
        title="Contradicting evidence"
        items={assessment.contradictions.map((c) => `${c.label} (Source: ${c.source})`)}
      />
      <NoticeList
        title="Missing critical inputs"
        items={assessment.missingCritical.map((m) => `${m.label} (Source: ${m.source})`)}
      />
    </Card>
  )
}
