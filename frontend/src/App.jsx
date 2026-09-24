
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchAisCleaning,
  fetchDetection,
  fetchHealth,
  fetchInvestigation,
  fetchTrajectories,
} from './api.js'
import { findCandidate, findTrajectory, rankingEntries } from './lib/format.js'
import AisPanel from './components/AisPanel.jsx'
import CandidateDetail from './components/CandidateDetail.jsx'
import CandidateTable from './components/CandidateTable.jsx'
import ConfidencePanel from './components/ConfidencePanel.jsx'
import EvidenceChain from './components/EvidenceChain.jsx'
import Header from './components/Header.jsx'
import MapPanel from './components/MapPanel.jsx'
import ObservationCard from './components/ObservationCard.jsx'
import OriginCard from './components/OriginCard.jsx'
import Timeline from './components/Timeline.jsx'
import Workflow from './components/Workflow.jsx'
import { Badge, Card, NoticeList, Spinner } from './components/ui.jsx'

const IDLE = { status: 'idle', data: null, error: null }

/**
 * Application shell.
 *
 * One core request (POST /investigate) drives the whole console; /detect adds
 * the satellite view and the AIS bundles load afterwards so the first paint is
 * fast. Each request owns its own status/error, so one failing panel never
 * blanks the rest of the dashboard.
 */
export default function App() {
  const [health, setHealth] = useState(IDLE)
  // The shared IDLE constant has status 'idle', but the core case is requested
  // immediately, so it starts in 'loading' and renders the boot screen from frame one.
  const [investigation, setInvestigation] = useState({ ...IDLE, status: 'loading' })
  const [detection, setDetection] = useState(IDLE)
  const [cleaning, setCleaning] = useState(IDLE)
  const [ais, setAis] = useState(IDLE)
  const [selected, setSelected] = useState(null)
  const [activeStep, setActiveStep] = useState('step-1')
  const [reloadToken, setReloadToken] = useState(0)

  const reload = useCallback(() => {
    setReloadToken((n) => n + 1)
    setSelected(null)
  }, [])

  /* --- core case load --------------------------------------------------- */
  useEffect(() => {
    const controller = new AbortController()

    setInvestigation(IDLE)
    setDetection(IDLE)
    setHealth(IDLE)

    fetchHealth({ signal: controller.signal })
      .then((body) => setHealth({ status: 'ready', data: body, error: null }))
      .catch((err) => {
        if (!controller.signal.aborted) setHealth({ status: 'error', data: null, error: err.message })
      })

    fetchInvestigation({}, { signal: controller.signal })
      .then((body) => {
        setInvestigation({ status: 'ready', data: body.investigation, error: null })
        setSelected(body.investigation?.statistics?.topCandidateMmsi || null)
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setInvestigation({ status: 'error', data: null, error: err.message })
        }
      })

    fetchDetection({ signal: controller.signal })
      .then((body) => setDetection({ status: 'ready', data: body.detection, error: null }))
      .catch((err) => {
        if (!controller.signal.aborted) setDetection({ status: 'error', data: null, error: err.message })
      })

    return () => controller.abort()
  }, [reloadToken])

  /* --- AIS bundles load after the core case ----------------------------- */
  useEffect(() => {
    if (investigation.status !== 'ready') return undefined
    const controller = new AbortController()

    setAis((prev) => ({ ...prev, status: 'loading', error: null }))
    setCleaning((prev) => ({ ...prev, status: 'loading', error: null }))

    fetchAisCleaning({ signal: controller.signal })
      .then((body) => setCleaning({ status: 'ready', data: body.cleaning, error: null }))
      .catch((err) => {
        if (!controller.signal.aborted) {
          setCleaning({ status: 'error', data: null, error: err.message })
        }
      })

    fetchTrajectories({ signal: controller.signal, timeoutMs: 60000 })
      .then((body) => setAis({ status: 'ready', data: body.trajectories, error: null }))
      .catch((err) => {
        if (!controller.signal.aborted) setAis({ status: 'error', data: null, error: err.message })
      })

    return () => controller.abort()
  }, [investigation.status, reloadToken])

  const selectedEntry = useMemo(
    () => findCandidate(investigation.data, selected),
    [investigation.data, selected],
  )
  const selectedTrack = useMemo(
    () => findTrajectory(ais.data, selected),
    [ais.data, selected],
  )

  const onStepSelect = useCallback((stepId, targetId) => {
    setActiveStep(stepId)
    const el = document.getElementById(targetId)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  /* --- states ----------------------------------------------------------- */
  // The core investigation is the console's backbone: until it has data we show
  // a full-screen state, never a half-built dashboard full of empty panels.
  if (!investigation.data) {
    if (investigation.status === 'error') {
      return (
        <div className="boot">
          <Card title="Cannot load the investigation" icon="⚠️">
            <p className="error-text">{investigation.error}</p>
            <ol className="howto">
              <li>
                Start the service:{' '}
                <code>cd intelligence &amp;&amp; ../.venv/bin/python -m uvicorn app.main:app --port 8000</code>
              </li>
              <li>
                Confirm it answers: <code>curl http://localhost:8000/health</code>
              </li>
              <li>
                Then reload this page — the dev server proxies <code>/api</code> to port 8000.
              </li>
            </ol>
            <button className="btn" onClick={reload}>Try again</button>
          </Card>
        </div>
      )
    }
    return (
      <div className="boot">
        <Spinner label="Loading CASE-001 from the ABYSS intelligence service…" />
        {health.error ? <p className="error-text">{health.error}</p> : null}
      </div>
    )
  }

  return (
    <div className="app">
      <Header
        investigation={investigation.data}
        detection={detection.data}
        health={health.data}
        loading={investigation.status === 'loading'}
        onReload={reload}
      />

      <Workflow
        investigation={investigation.data}
        detection={detection.data}
        ais={ais.data}
        aisStatus={ais.status}
        status={investigation.status}
        active={activeStep}
        onSelect={onStepSelect}
      />

      <main className="layout">
        {/* Top row: the three "what happened" panels side by side, so a tall
            panel never leaves a tall empty gap in its neighbour. */}
        <div className="col col-full top-grid">
          <ObservationCard
            detection={detection.data}
            loading={detection.status === 'loading'}
            error={detection.error}
            onRetry={reload}
          />
          <OriginCard investigation={investigation.data} />
          <ConfidencePanel investigation={investigation.data} />
        </div>

        <div className="col col-full">
          <MapPanel
            trajectories={ais.data}
            investigation={investigation.data}
            detection={detection.data}
            trajectory={selectedTrack}
            selected={selected}
            onClearSelection={() => setSelected(null)}
          />
        </div>

        <div className="col col-full">
          <AisPanel
            cleaning={cleaning.data}
            trajectories={ais.data}
            loading={ais.status === 'loading'}
            error={ais.error}
            onRetry={reload}
          />
        </div>

        <div className="col col-table">
          <CandidateTable
            investigation={investigation.data}
            selected={selected}
            onSelect={(mmsi) => {
              setSelected(String(selected) === String(mmsi) ? null : mmsi)
              setActiveStep('step-7')
            }}
          />
        </div>

        <div className="col col-detail">
          <CandidateDetail entry={selectedEntry} trajectory={selectedTrack} />
        </div>

        {/* Phase 16: the case chronology. Vessel rows in it re-select a candidate,
            so the timeline, map, evidence panel and chain stay in step. */}
        <div className="col col-full">
          <Timeline
            investigation={investigation.data}
            detection={detection.data}
            selected={selected}
            onSelect={(mmsi) => setSelected(String(mmsi))}
          />
        </div>

        {/* Phase 17: why the selected candidate holds its priority, as the
            method's own cascade with per-node API provenance. */}
        <div className="col col-full">
          <EvidenceChain
            investigation={investigation.data}
            detection={detection.data}
            selected={selected}
            trajectory={selectedTrack}
            onSelect={(mmsi) => setSelected(String(mmsi))}
          />
        </div>

        <div className="col col-full">
          <Card
            id="provenance"
            title="Provenance, warnings & limitations"
            subtitle="Exactly what the service said about this case"
            icon="📋"
            actions={<Badge tone="demo">synthetic demo data</Badge>}
          >
            <div className="detail-columns">
              <div>
                <NoticeList tone="warn" title="Service warnings" items={investigation.data?.warnings} />
                <NoticeList tone="warn" title="Investigation notes" items={investigation.data?.notes} />
              </div>
              <div>
                <NoticeList title="Known limitations" items={investigation.data?.limitations} />
                <NoticeList tone="info" title="Region notes" items={investigation.data?.origin?.notes} />
              </div>
            </div>
            <p className="fine-print">
              {rankingEntries(investigation.data).length} vessels ranked · case{' '}
              <span className="mono">{investigation.data?.caseId}</span> · dataset{' '}
              {investigation.data?.datasetLabel}
            </p>
          </Card>
        </div>
      </main>

      <footer className="app-footer">
        <span>ABYSS Intelligence Console — forensic investigation console for the intelligence API.</span>
        <span>Analytical evidence for investigation support; not a legal determination.</span>
      </footer>
    </div>
  )
}

