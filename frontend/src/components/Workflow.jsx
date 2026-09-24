/** The analyst-facing pipeline: observation through ranked review. */
import { fmtInt, rankingEntries } from '../lib/format.js'

const STEPS = [
  { id: 'step-1', n: 1, title: 'Satellite observation', detail: 'Detection verdict & confidence', target: 'observation' },
  { id: 'step-2', n: 2, title: 'Oil slick characterisation', detail: 'Polygon geometry & look-alike screen', target: 'observation' },
  { id: 'step-3', n: 3, title: 'Backward drift / origin', detail: 'Probable region & release window', target: 'origin' },
  { id: 'step-4', n: 4, title: 'Historical AIS filtering', detail: 'Clean, reconstructed vessel tracks', target: 'ais' },
  { id: 'step-5', n: 5, title: 'Vessel behaviour analysis', detail: 'Baseline, gap & movement context', target: 'ais' },
  { id: 'step-6', n: 6, title: 'Evidence scoring', detail: 'Five explainable compatibility factors', target: 'candidate-detail' },
  { id: 'step-7', n: 7, title: 'Candidate ranking', detail: 'Priority order for analyst review', target: 'candidates' },
]

const STATE_LABELS = {
  done: 'complete',
  flagged: 'review',
  active: 'loading',
  pending: 'queued',
  unknown: 'unavailable',
}

export default function Workflow({ investigation, detection, ais, aisStatus = 'idle', status, active, onSelect }) {
  const stats = investigation?.statistics || {}
  const entries = rankingEntries(investigation)
  const hasAisTracks = Array.isArray(ais?.trajectories) && ais.trajectories.length > 0
  const hasFactors = entries.some((entry) => entry.factors && Object.keys(entry.factors).length > 0)

  const stepState = (step) => {
    if (status === 'error') return 'unknown'
    if (status === 'loading') return 'pending'
    switch (step.n) {
      case 1:
        return detection ? (detection.detected ? 'done' : 'flagged') : 'pending'
      case 2:
        return detection?.characterisation ? 'done' : 'pending'
      case 3:
        return investigation?.origin?.region?.geometry ? 'done' : 'pending'
      case 4:
        if (aisStatus === 'loading') return 'active'
        return hasAisTracks || Number.isFinite(stats.recordsCleaned) ? 'done' : 'pending'
      case 5:
        if (aisStatus === 'loading') return 'active'
        return Number.isFinite(stats.behaviourAnomaliesReported) || hasAisTracks ? 'done' : 'pending'
      case 6:
        return hasFactors ? 'done' : 'pending'
      case 7:
        return entries.length > 0 ? 'done' : 'pending'
      default:
        return 'pending'
    }
  }

  return (
    <nav className="workflow" aria-label="Seven-stage investigation workflow">
      <div className="workflow-heading">
        <div>
          <span className="eyebrow">Investigation pipeline</span>
          <h2>From observation to ranked review</h2>
        </div>
        <span className="workflow-case mono">{investigation?.caseId || 'CASE-001'}</span>
      </div>
      <div className="workflow-track">
        {STEPS.map((step, index) => {
          const state = stepState(step)
          return (
            <div className="workflow-node" key={step.id}>
              <button
                id={step.id}
                className={`step step-${state} ${active === step.id ? 'step-active' : ''}`}
                onClick={() => onSelect(step.id, step.target)}
                aria-current={active === step.id ? 'step' : undefined}
                aria-label={`${step.n}. ${step.title}: ${STATE_LABELS[state]}`}
              >
                <span className="step-top">
                  <span className="step-n">{state === 'done' ? '✓' : step.n}</span>
                  <span className="step-state">{STATE_LABELS[state]}</span>
                </span>
                <span className="step-text">
                  <strong>{step.title}</strong>
                  <small>{step.detail}</small>
                </span>
              </button>
              {index < STEPS.length - 1 ? <span className="step-arrow" aria-hidden="true">→</span> : null}
            </div>
          )
        })}
      </div>
      <div className="workflow-summary">
        <span><strong>{fmtInt(stats.vesselsScored)}</strong> vessels scored</span>
        <span><strong>{fmtInt(stats.recordsCleaned)}</strong> AIS reports cleaned</span>
        <span><strong>{fmtInt(stats.insideRegionDuringWindow)}</strong> inside region in window</span>
        <span><strong>{fmtInt(stats.gapsJudged)}</strong> gaps judged</span>
      </div>
    </nav>
  )
}
