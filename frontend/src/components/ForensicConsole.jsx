import { useMemo } from 'react'
import EvidenceSufficiencyPanel from './EvidenceSufficiencyPanel.jsx'
import UncertaintyPanel from './UncertaintyPanel.jsx'
import HypothesisPanel from './HypothesisPanel.jsx'
import CandidateComparison from './CandidateComparison.jsx'
import HypothesisReplay from './HypothesisReplay.jsx'
import NextEvidencePanel from './NextEvidencePanel.jsx'
import { buildForensicAssessment } from '../lib/forensics.js'
import { findCandidate } from '../lib/format.js'

/**
 * The forensic console: one coherent uncertainty-aware investigation view.
 *
 * A single `buildForensicAssessment` call computes everything the panels
 * share (sufficiency, uncertainty, status), so no two panels recompute the
 * same thing and the numbers cannot drift between them. The console is
 * mounted inside the review stage for the selected candidate vessel.
 *
 * Order follows the brief: status → sufficiency → comparison →
 * uncertainty → hypotheses → replay → next evidence.
 */
export default function ForensicConsole({ investigation, detection, selected, trajectory, forecast }) {
  const candidate = useMemo(
    () => findCandidate(investigation, selected),
    [investigation, selected],
  )

  const assessment = useMemo(
    () => (candidate
      ? buildForensicAssessment({ investigation, detection, candidate, trajectory, forecast })
      : null),
    [investigation, detection, candidate, trajectory, forecast],
  )

  const candidateName = candidate ? candidate.name || `MMSI ${candidate.mmsi}` : null

  return (
    <div style={{ display: 'grid', gap: '20px' }}>
      <NextEvidencePanel status={assessment?.status} next={assessment?.nextEvidence} />
      <EvidenceSufficiencyPanel assessment={assessment?.sufficiency} name={candidateName} />
      <CandidateComparison investigation={investigation} detection={detection} mmsiA={candidate?.mmsi} />
      <UncertaintyPanel chain={assessment?.uncertainty} />
      <HypothesisPanel result={assessment?.hypotheses} />
      <HypothesisReplay replay={assessment?.replay} />
    </div>
  )
}
