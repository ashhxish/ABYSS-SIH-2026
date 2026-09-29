import { useMemo, useState } from 'react'
import { Badge, Bar, Card, Empty } from './ui.jsx'
import { MeterRow, Provenance, SectionHead } from './forensicShared.jsx'
import { compareCandidates } from '../lib/forensics.js'
import { rankingEntries } from '../lib/format.js'

/**
 * Feature 4 — Compare Candidates.
 *
 * Compares the currently selected candidate (A) against another candidate (B)
 * chosen from the ranking, axis by axis. All values come verbatim from
 * `compareCandidates`, which reads the engine's own numbers. Framed strictly
 * as higher/lower evidence compatibility and investigation priority.
 */
function AxisRow({ axis }) {
  const winnerLabel = axis.winner === 'a' ? 'A leads' : axis.winner === 'b' ? 'B leads' : 'tied / not decidable'
  const winnerTone = axis.winner == null ? 'neutral' : 'accent'
  return (
    <div className="factor-row">
      <div className="factor-head">
        <strong>{axis.label}</strong>
        <Badge tone={winnerTone}>{winnerLabel}</Badge>
      </div>
      <div className="detail-columns">
        <div>
          <p className="fine-print mono">A · {axis.a.display}</p>
          {axis.a.percent == null ? null : <Bar percent={axis.a.percent} tone={axis.winner === 'a' ? 'ok' : 'accent'} label={`A ${axis.a.display}`} />}
        </div>
        <div>
          <p className="fine-print mono">B · {axis.b.display}</p>
          {axis.b.percent == null ? null : <Bar percent={axis.b.percent} tone={axis.winner === 'b' ? 'ok' : 'accent'} label={`B ${axis.b.display}`} />}
        </div>
      </div>
      {axis.note ? <p className="fine-print">{axis.note}</p> : null}
      <Provenance source={axis.source} />
    </div>
  )
}

export default function CandidateComparison({ investigation, detection, mmsiA, onSelectB }) {
  const entries = useMemo(() => rankingEntries(investigation), [investigation])
  const defaultB = entries.find((e) => String(e.mmsi) !== String(mmsiA))?.mmsi ?? null
  const [mmsiB, setMmsiB] = useState(null)
  const activeB = mmsiB ?? defaultB

  const comparison = useMemo(
    () => (mmsiA && activeB
      ? compareCandidates({ investigation, detection, mmsiA, mmsiB: activeB })
      : null),
    [investigation, detection, mmsiA, activeB],
  )

  if (!mmsiA || entries.length === 0) {
    return (
      <Card id="compare-candidates" title="Compare candidates" subtitle="Selected candidate against another candidate" icon="⚔️">
        <Empty>Select a candidate vessel in the ranking to compare it against another candidate.</Empty>
      </Card>
    )
  }

  const pickB = (mmsi) => {
    setMmsiB(mmsi)
    if (onSelectB) onSelectB(mmsi)
  }

  return (
    <Card
      id="compare-candidates"
      title="Compare candidates"
      subtitle="Why candidate A ranks differently from candidate B — evidence compatibility only"
      icon="⚔️"
    >
      <div className="candidate-selector-bar">
        <span className="selector-label">COMPARE AGAINST</span>
        <div className="candidate-chips">
          {entries.map((e) => {
            const isSel = String(e.mmsi) === String(activeB)
            const isA = String(e.mmsi) === String(mmsiA)
            return (
              <button
                key={e.mmsi}
                type="button"
                className={`btn btn-chip ${isSel ? 'btn-primary' : ''}`}
                disabled={isA}
                title={isA ? 'Candidate A (currently selected)' : `Compare against ${e.name || e.mmsi}`}
                onClick={() => pickB(e.mmsi)}
              >
                {isA ? `A · ${e.name || e.mmsi}` : `${e.name || e.mmsi}`}
              </button>
            )
          })}
        </div>
      </div>

      {!comparison || !comparison.available ? (
        <Empty>{comparison?.reason || 'Comparison is unavailable for these candidates.'}</Empty>
      ) : (
        <>
          <p className="fine-print"><strong>{comparison.summary}</strong></p>

          <SectionHead>Candidate A ranks differently because</SectionHead>
          {comparison.aAdvantages.length === 0 ? (
            <p className="fine-print">No axis separates candidate A from candidate B on the available evidence.</p>
          ) : (
            <ul className="reason-list">
              {comparison.aAdvantages.map((adv, i) => (
                <li key={i}>+ {adv.text} <span className="muted">({adv.label})</span></li>
              ))}
            </ul>
          )}

          <SectionHead>Counter-points for candidate B</SectionHead>
          {comparison.bAdvantages.length === 0 ? (
            <p className="fine-print">No axis separates candidate B from candidate A on the available evidence.</p>
          ) : (
            <ul className="reason-list">
              {comparison.bAdvantages.map((adv, i) => (
                <li key={i}>+ {adv.text} <span className="muted">({adv.label})</span></li>
              ))}
            </ul>
          )}

          <SectionHead>Axis-by-axis comparison</SectionHead>
          <div className="factor-list">
            {comparison.axes.map((axis) => <AxisRow key={axis.key} axis={axis} />)}
          </div>

          <p className="fine-print">{comparison.note}</p>
        </>
      )}
    </Card>
  )
}
