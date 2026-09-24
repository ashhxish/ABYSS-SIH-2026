import { useMemo } from 'react'
import { fmtNumber, rankingEntries, scoreBand } from '../lib/format.js'
import { buildEvidenceChain } from '../lib/evidence.js'
import { Badge, Card, Empty } from './ui.jsx'

const STATUS_TONE = {
  OBSERVED: 'ok',
  PRIOR: 'info',
  MODELLED: 'accent',
  ANALYTICAL: 'neutral',
}

function ChainNode({ item }) {
  const classes = ['ec-node', `ec-${String(item.status).toLowerCase()}`]
  if (item.unavailableReason) classes.push('ec-unavailable')
  return (
    <li className={classes.join(' ')}>
      <div className="ec-node-head">
        <strong>{item.title}</strong>
        <span className="ec-chips">
          <Badge tone={STATUS_TONE[item.status] || 'neutral'}>{item.status}</Badge>
          {item.unavailableReason ? <Badge tone="warn">unavailable</Badge> : null}
        </span>
      </div>
      {item.unavailableReason ? (
        <p className="ec-note">{item.unavailableReason}</p>
      ) : (
        <>
          {item.summary ? <p className="ec-summary">{item.summary}</p> : null}
          {item.metrics.length > 0 ? (
            <dl className="ec-metrics">
              {item.metrics.map((entry) => (
                <div key={entry.label}>
                  <dt>{entry.label}</dt>
                  <dd className="mono">{entry.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </>
      )}
      <span className="ec-source mono" title="API field this node was read from">
        Source: {item.source}
      </span>
    </li>
  )
}

/**
 * Phase 17 - forensic evidence chain.
 *
 * Explains "why did this candidate receive this investigation priority?" using
 * the method's own cascade: observed data -> modelled inference -> AIS
 * correlation -> evidence compatibility -> candidate ranking. Every score shown
 * is the API's own; nothing is re-scored or invented here.
 */
export default function EvidenceChain({ investigation, detection, selected, trajectory, onSelect }) {
  const entries = useMemo(() => rankingEntries(investigation), [investigation])
  const chain = useMemo(
    () => buildEvidenceChain(investigation, detection, selected, trajectory),
    [investigation, detection, selected, trajectory],
  )
  const band = scoreBand(chain.totalScore)

  if (!investigation) {
    return (
      <Card id="evidence-chain" title="Evidence chain" icon="🧩">
        <Empty>The chain is built from the investigation response, which has not loaded.</Empty>
      </Card>
    )
  }

  if (!selected || !chain.available) {
    return (
      <Card
        id="evidence-chain"
        title="Evidence chain"
        subtitle="Observation → origin → AIS correlation → compatibility → ranking"
        icon="🧩"
      >
        <Empty>{chain.reason || 'Select a candidate in the ranking to trace its evidence chain.'}</Empty>
      </Card>
    )
  }

  const others = entries.filter((entry) => String(entry.mmsi) !== String(selected))

  return (
    <Card
      id="evidence-chain"
      title={chain.name || `MMSI ${chain.mmsi}`}
      subtitle={`Evidence chain · rank ${chain.rank} of ${entries.length} · MMSI ${chain.mmsi}`}
      icon="🧩"
      actions={
        <span className="ec-score">
          <span className="mono">{fmtNumber(chain.totalScore, 1)} / 100</span>
          <Badge tone={band.tone}>{band.label}</Badge>
        </span>
      }
    >
      <p className="fine-print">
        Investigation priority aggregates compatible evidence to order analyst review. It is{' '}
        <strong>not a probability of responsibility</strong>, and no vessel is described as responsible here.
      </p>

      <section className="summary-block">
        <h3 className="sub-head">Chain narrative</h3>
        <ol className="summary-flow">
          {chain.narrative.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ol>
      </section>

      <div className="ec-flow">
        {chain.layers.map((layer, index) => (
          <section className="ec-layer" key={layer.id}>
            <header className="ec-layer-head">
              <span className="ec-layer-n mono">{index + 1}</span>
              <div>
                <h3 className="sub-head">{layer.title}</h3>
                <p className="ec-caption">{layer.caption}</p>
              </div>
              <span className="muted mono">{layer.nodes.length}</span>
            </header>
            <ul className="ec-nodes">
              {layer.nodes.map((item) => (
                <ChainNode key={item.id} item={item} />
              ))}
            </ul>
            {index < chain.layers.length - 1 ? (
              <span className="ec-arrow" aria-hidden="true">
                ↓ feeds into
              </span>
            ) : null}
          </section>
        ))}
      </div>

      <section className="summary-block">
        <h3 className="sub-head">Counterfactual comparison</h3>
        {chain.counterfactual.available ? (
          <>
            <p>{chain.counterfactual.text}</p>
            <div className="delta-list">
              {Object.entries(chain.counterfactual.deltas || {}).map(([key, delta]) => (
                <Badge key={key} tone={Number(delta) > 0 ? 'ok' : 'neutral'}>
                  {key} {Number(delta) > 0 ? '+' : ''}
                  {fmtNumber(delta, 3)}
                </Badge>
              ))}
            </div>
            <p className="fine-print mono">Source: ranking[].counterfactual</p>
          </>
        ) : (
          <p className="ec-note">Counterfactual comparison unavailable.</p>
        )}
      </section>

      {others.length > 0 ? (
        <section className="ec-context">
          <h3 className="sub-head">Other candidates (context)</h3>
          <p className="fine-print">
            De-emphasised for comparison. Selecting one re-traces the chain for that vessel.
          </p>
          <div className="ec-others">
            {others.map((entry) => (
              <button
                type="button"
                key={entry.mmsi}
                className="ec-other"
                onClick={() => onSelect && onSelect(entry.mmsi)}
                title={`Trace the evidence chain for ${entry.name || entry.mmsi}`}
              >
                <span className="ec-other-rank mono">#{entry.rank}</span>
                <span className="ec-other-name">{entry.name || `MMSI ${entry.mmsi}`}</span>
                <span className="ec-other-score mono">{fmtNumber(entry.totalScore, 1)}</span>
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </Card>
  )
}
