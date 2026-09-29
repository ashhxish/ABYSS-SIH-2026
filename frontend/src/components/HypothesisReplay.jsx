import { Badge, Card, Empty } from './ui.jsx'
import { Provenance, SectionHead } from './forensicShared.jsx'
import { ReplayPlot } from './HypothesisReplayPlot.jsx'

/**
 * Feature 5 — Hypothesis Replay (part 2: stages, checks and answer).
 *
 * The plot is `ReplayPlot`; this card owns the stage list, the engine’s
 * own compatibility checks and the consistency answer. Reads ONLY from
 * `buildHypothesisReplay` output — no geometry or numbers are invented here.
 */
export default function HypothesisReplay({ replay }) {
  if (!replay) {
    return (
      <Card id="hypothesis-replay" title="Hypothesis replay" subtitle="Candidate trajectory → origin region → observed slick" icon="🎞️">
        <Empty>Replay is unavailable until an investigation response loads.</Empty>
      </Card>
    )
  }
  if (!replay.available) {
    return (
      <Card id="hypothesis-replay" title="Hypothesis replay" subtitle="Candidate trajectory → origin region → observed slick" icon="🎞️">
        <Empty>{replay.reason}</Empty>
      </Card>
    )
  }

  return (
    <Card
      id="hypothesis-replay"
      title="Hypothesis replay"
      subtitle={`Could ${replay.candidate.name}’s recorded movement be consistent with the observed event?`}
      icon="🎞️"
      actions={<Badge tone={replay.compatibility.failed.length === 0 ? 'ok' : 'warn'}>{replay.compatibility.summary}</Badge>}
    >
      <p className="fine-print"><strong>{replay.question}</strong></p>
      <ReplayPlot geo={replay.geo} />
      <div className="legend">
        <span><i className="key key-track" /> candidate track</span>
        <span><i className="key key-region" /> probable origin region</span>
        <span><i className="key key-drift" /> modelled backward drift</span>
        <span><i className="key key-slick" /> observed slick</span>
        <span className="legend-note">forward replay shown dashed rose when supplied · schematic plot, not for navigation</span>
      </div>
      <p className="fine-print">{replay.frameNote}</p>

      <SectionHead>Replay stages — existing data only</SectionHead>
      <div className="factor-list">
        {replay.stages.map((stage) => (
          <div className="factor-row" key={stage.id}>
            <div className="factor-head">
              <strong>{stage.label}</strong>
              <Badge tone={stage.available ? 'ok' : 'neutral'}>{stage.available ? 'available' : 'not available'}</Badge>
            </div>
            <p className="fine-print">{stage.caption}</p>
            <p className="fine-print"><strong>{stage.display}</strong></p>
            {stage.detail ? <p className="fine-print">{stage.detail}</p> : null}
            {stage.note ? <p className="fine-print">{stage.note}</p> : null}
            <Provenance source={stage.source} />
          </div>
        ))}
      </div>

      <SectionHead>Engine compatibility checks</SectionHead>
      <ul className="reason-list">
        {replay.compatibility.checks.map((check) => (
          <li key={check.key}>
            {check.pass ? '✓' : '✕'} {check.label}{' '}
            <span className="fine-print mono">Source: {check.source}</span>
          </li>
        ))}
      </ul>

      <SectionHead>Answer</SectionHead>
      <p className="fine-print"><strong>{replay.answer}</strong></p>
      <p className="fine-print">
        Forward model: {replay.forward.message}. No overlap percentage is
        computed — the system publishes no calibrated overlap or error metric.
      </p>
      <p className="fine-print">{replay.standing}</p>
    </Card>
  )
}
