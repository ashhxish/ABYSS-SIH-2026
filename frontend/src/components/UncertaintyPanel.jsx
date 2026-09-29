import { Badge, Card, Empty, NoticeList } from './ui.jsx'
import { EvidencePoint, Provenance, SectionHead } from './forensicShared.jsx'

/**
 * Feature 2 — Uncertainty propagation.
 *
 * Renders the observation → origin → window → correlation → confidence
 * cascade from `uncertaintyChain`. Layers the API said nothing about render
 * as “Not available”; the model’s own spread is surfaced only when published.
 */
export default function UncertaintyPanel({ chain }) {
  if (!chain || !Array.isArray(chain.layers)) {
    return (
      <Card id="uncertainty-chain" title="Uncertainty" subtitle="Observation → investigation confidence" icon="🌫️">
        <Empty>Uncertainty layers are unavailable until an investigation response loads.</Empty>
      </Card>
    )
  }

  return (
    <Card
      id="uncertainty-chain"
      title="Uncertainty"
      subtitle="Observation → origin → release window → vessel correlation → investigation confidence"
      icon="🌫️"
    >
      <div className="ec-flow">
        {chain.layers.map((layer, index) => (
          <section className="ec-layer" key={layer.id}>
            <header className="ec-layer-head">
              <span className="ec-layer-n mono">{index + 1}</span>
              <div>
                <h3 className="sub-head">{layer.label}</h3>
                <p className="ec-caption">{layer.caption}</p>
              </div>
              <Badge tone={layer.available ? 'accent' : 'neutral'}>{layer.display}</Badge>
            </header>
            {layer.detail ? <p className="ec-note">{layer.detail}</p> : null}
            {layer.note ? <p className="fine-print">{layer.note}</p> : null}
            <Provenance source={layer.source} />
            {index < chain.layers.length - 1 ? (
              <span className="ec-arrow" aria-hidden="true">↓ feeds into</span>
            ) : null}
          </section>
        ))}
      </div>

      <SectionHead>Uncertainty carried forward</SectionHead>
      <p className="fine-print">{chain.uncertaintyNote}</p>

      <SectionHead>Model spread (API-published only)</SectionHead>
      <p className="fine-print">
        {chain.radiusDisplay} <span className="mono">Source: {chain.radiusSource}</span>
      </p>
    </Card>
  )
}
