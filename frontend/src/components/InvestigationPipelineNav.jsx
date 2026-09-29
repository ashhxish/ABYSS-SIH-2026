import React from 'react'

const STAGES = [
  { id: 'detect', num: '01', label: 'DETECT' },
  { id: 'origin', num: '02', label: 'ORIGIN' },
  { id: 'hindcast', num: '03', label: 'HINDCAST' },
  { id: 'forecast', num: '04', label: 'FORECAST' },
  { id: 'ais', num: '05', label: 'AIS' },
  { id: 'behaviour', num: '06', label: 'BEHAVIOUR' },
  { id: 'evidence', num: '07', label: 'EVIDENCE' },
  { id: 'review', num: '08', label: 'REVIEW' },
]

export default function InvestigationPipelineNav({
  currentStage,
  completedStages = [],
  onSelectStage,
  onExitToHome,
}) {
  const currentIndex = STAGES.findIndex((s) => s.id === currentStage)

  return (
    <div className="investigation-pipeline-nav">
      <div className="pipeline-nav-left">
        <button
          type="button"
          className="btn btn-ghost btn-sm btn-nav-home"
          onClick={onExitToHome}
          title="Return to investigation home"
        >
          ⌂ HOME
        </button>
      </div>

      <div className="pipeline-nav-steps">
        {STAGES.map((step, idx) => {
          const isCurrent = step.id === currentStage
          const isCompleted = completedStages.includes(step.id) || idx < currentIndex
          const isAccessible = isCompleted || idx <= currentIndex + 1

          return (
            <button
              key={step.id}
              type="button"
              className={`pipeline-nav-item ${isCurrent ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}
              onClick={() => isAccessible && onSelectStage(step.id)}
              disabled={!isAccessible}
            >
              <span className="nav-step-icon">
                {isCompleted && !isCurrent ? '✓' : isCurrent ? '◉' : '○'}
              </span>
              <span className="nav-step-num">{step.num}</span>
              <span className="nav-step-label">{step.label}</span>
              {idx < STAGES.length - 1 && <span className="nav-step-separator">➔</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
