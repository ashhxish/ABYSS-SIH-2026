import React from 'react'
import { Badge } from './ui.jsx'

export default function InvestigationHome({
  onStartInvestigation,
  dataSource,
  onSelectDataSource,
  investigationStatus,
}) {
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

  return (
    <div className="investigation-home">
      <div className="home-hero">
        <div className="home-badge-row">
          <Badge tone="accent">MARITIME FORENSIC INTELLIGENCE</Badge>
          <Badge tone={dataSource === 'case-001' ? 'demo' : 'ok'}>
            {dataSource === 'case-001' ? 'CASE-001 (SYNTHETIC VERIFIED)' : 'REAL SATELLITE & AIS WORKSPACE'}
          </Badge>
        </div>
        <h1 className="home-title">ABYSS</h1>
        <p className="home-tagline">Detect → Reconstruct → Correlate → Explain</p>
        <p className="home-description">
          Automated satellite radar oil slick detection, hydrodynamic drift hindcast/forecast,
          and forensic AIS candidate correlation with strict non-fabrication guarantees.
        </p>

        <div className="home-cta-box">
          <div className="data-mode-select">
            <span className="mode-label">DATASET SOURCE:</span>
            <div className="mode-buttons">
              <button
                type="button"
                className={`btn ${dataSource === 'case-001' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => onSelectDataSource('case-001')}
              >
                CASE-001 Golden Demo
              </button>
              <button
                type="button"
                className={`btn ${dataSource === 'sentinel1' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => onSelectDataSource('sentinel1')}
              >
                🛰️ Real Sentinel-1 &amp; NOAA AIS
              </button>
            </div>
          </div>

          <button
            type="button"
            className="btn btn-primary btn-large btn-start-investigation"
            onClick={onStartInvestigation}
            disabled={investigationStatus === 'loading'}
          >
            {investigationStatus === 'loading' ? 'INITIALIZING WORKSPACE…' : '▶ START INVESTIGATION'}
          </button>
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
