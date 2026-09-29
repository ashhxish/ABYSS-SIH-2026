import React from 'react'
import { Badge } from './ui.jsx'
import { isSentinel1Configured } from '../api.js'

/**
 * Entry screen for the investigation console.
 *
 * The primary action is the self-contained CASE-001 synthetic demonstration,
 * which runs entirely on bundled offline data and needs no external scene file.
 * Real Sentinel-1 work is an explicit, clearly-labelled secondary path that is
 * only shown as configured when a scene is actually available.
 */
export default function InvestigationHome({
  onStartInvestigation,
  dataSource,
  onSelectDataSource,
  investigationStatus,
}) {
  const isDemo = dataSource !== 'sentinel1'
  const realConfigured = isSentinel1Configured()

  const pipelineSteps = [
    { num: '01', id: 'detect', label: 'DETECT', desc: 'Sentinel-1 SAR / U-Net slick segmentation' },
    { num: '02', id: 'origin', label: 'ORIGIN', desc: 'Reverse transport & probable origin reconstruction' },
    { num: '03', id: 'hindcast', label: 'HINDCAST', desc: 'Ocean current & windage backdrift ensemble' },
    { num: '04', id: 'forecast', label: 'FORECAST', desc: 'Forward trajectory & dispersal footprint' },
    { num: '05', id: 'ais', label: 'AIS FORENSICS', desc: 'Candidate spatio-temporal vessel correlation' },
    { num: '06', id: 'behaviour', label: 'BEHAVIOUR', desc: 'Speed anomalies, loitering & AIS gap detection' },
    { num: '07', id: 'evidence', label: 'EVIDENCE FUSION', desc: 'Multi-criteria forensic matrix & attribution audit' },
    { num: '08', id: 'review', label: 'INVESTIGATOR REVIEW', desc: 'Evidence chain, counterfactuals & final dossier' },
  ]

  // The demo path always resolves to CASE-001 first, so returning to this
  // screen can never leave the console pointed at a scene-less real-data mode.
  const startDemo = () => {
    onSelectDataSource('case-001')
    onStartInvestigation()
  }

  const startReal = () => {
    onSelectDataSource('sentinel1')
    onStartInvestigation()
  }

  return (
    <div className="investigation-home">
      <div className="home-hero">
        <div className="home-badge-row">
          <Badge tone="accent">MARITIME FORENSIC INTELLIGENCE</Badge>
          <Badge tone={isDemo ? 'demo' : 'ok'}>
            {isDemo ? 'CASE-001 (SYNTHETIC VERIFIED)' : 'REAL SATELLITE & AIS WORKSPACE'}
          </Badge>
        </div>
        <h1 className="home-title">ABYSS</h1>
        <p className="home-subtitle">AI-Powered Maritime Oil Spill Forensics</p>
        <p className="home-tagline">Detect → Reconstruct → Correlate → Explain</p>
        <p className="home-description">
          Reconstruct the probable spill origin, correlate vessel movements, and build an
          explainable evidence chain. Automated SAR slick detection, hydrodynamic
          hindcast/forecast, and forensic AIS candidate correlation with strict
          non-fabrication guarantees.
        </p>

        <div className="home-cta-box">
          <div className="demo-case-label">CASE-001 · Synthetic Demonstration</div>

          <button
            type="button"
            className="btn btn-primary btn-large btn-start-investigation"
            onClick={startDemo}
            disabled={investigationStatus === 'loading'}
          >
            {investigationStatus === 'loading' ? 'INITIALIZING WORKSPACE…' : '▶ START DEMO INVESTIGATION'}
          </button>

          <p className="cta-note">
            Runs offline on bundled demonstration data. No satellite scene file or API key required.
          </p>

          <div className="home-secondary">
            <span className="mode-label">ADVANCED REAL-DATA PATH</span>
            <button type="button" className="btn btn-ghost" onClick={startReal}>
              🛰️ Real Sentinel-1 Investigation
            </button>
            <span className="mode-note">
              {realConfigured
                ? 'A Sentinel-1 VV+VH scene is configured for this build.'
                : 'Optional. Requires a Sentinel-1 VV+VH scene to be configured for the service (VITE_SENTINEL1_SCENE_PATH). Not needed for the demonstration.'}
            </span>
          </div>
        </div>
      </div>

      <div className="home-pipeline-section">
        <h2 className="pipeline-heading">INVESTIGATION PIPELINE WORKFLOW</h2>
        <div className="pipeline-grid">
          {pipelineSteps.map((step) => (
            <div key={step.id} className="pipeline-card">
              <div className="pipeline-num">{step.num}</div>
              <div className="pipeline-content">
                <h3 className="pipeline-name">{step.label}</h3>
                <p className="pipeline-desc">{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
