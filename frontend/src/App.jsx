import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchInvestigation,
  fetchAisCleaning,
  fetchTrajectories,
  fetchDetection,
  fetchRealAisAnalyze,
  fetchSentinel1Detect,
  fetchRealDriftSimulate,
  SENTINEL1_SCENE_PATH,
  isSentinel1Configured,
} from './api.js'
import Header from './components/Header.jsx'
import InvestigationHome from './components/InvestigationHome.jsx'
import InvestigationPipelineNav from './components/InvestigationPipelineNav.jsx'
import UnifiedMapPanel from './components/UnifiedMapPanel.jsx'
import DetectionStagePanel from './components/DetectionStagePanel.jsx'
import OriginReconstructionPanel from './components/OriginReconstructionPanel.jsx'
import HindcastStagePanel from './components/HindcastStagePanel.jsx'
import ForecastStagePanel from './components/ForecastStagePanel.jsx'
import RealAisPanel from './components/RealAisPanel.jsx'
import BehaviourStagePanel from './components/BehaviourStagePanel.jsx'
import EvidenceFusionPanel from './components/EvidenceFusionPanel.jsx'
import InvestigatorReviewPanel from './components/InvestigatorReviewPanel.jsx'
import Timeline from './components/Timeline.jsx'
import EvidenceChain from './components/EvidenceChain.jsx'
import CandidateTable from './components/CandidateTable.jsx'
import CandidateDetail from './components/CandidateDetail.jsx'
import { Card, Spinner } from './components/ui.jsx'
import { sceneBoundsOf } from './lib/realais.js'
import {
  findCandidate,
  findTrajectory,
  rankingEntries,
} from './lib/format.js'

/**
 * Local App.jsx helpers delegate to the tested lib builders so the workspace
 * reads the same CASE-001 shapes (`ranking.entries`, `origin.*`,
 * `detection.*`) that the canonical panels use.
 */

export default function App() {
  const [viewState, setViewState] = useState('home') // 'home' | 'workspace'
  const [stage, setStage] = useState('detect') // 'detect' | 'origin' | 'hindcast' | 'forecast' | 'ais' | 'behaviour' | 'evidence' | 'review'
  const [completedStages, setCompletedStages] = useState([])
  const [selected, setSelected] = useState(null)
  const [viewMode, setViewMode] = useState('synthetic') // 'synthetic' | 'sentinel1'
  const [showEvidenceChainModal, setShowEvidenceChainModal] = useState(false)

  // Asynchronous dataset states
  const [investigation, setInvestigation] = useState({ status: 'loading', data: null, error: null })
  const [detection, setDetection] = useState({ status: 'idle', data: null, error: null })
  const [cleaning, setCleaning] = useState({ status: 'idle', data: null, error: null })
  const [ais, setAis] = useState({ status: 'idle', data: null, error: null })

  // Real Sentinel-1 & AIS states
  const [s1Data, setS1Data] = useState({ status: 'idle', data: null, error: null })
  const [realAis, setRealAis] = useState({ status: 'idle', data: null, error: null })

  // Phase 22 Drift simulation states
  const [driftHindcast, setDriftHindcast] = useState(null)
  const [driftForecast, setDriftForecast] = useState(null)
  const [driftLoading, setDriftLoading] = useState(false)
  const [forecastLoading, setForecastLoading] = useState(false)

  /* --- Initial Load: CASE-001 Synthetic Baseline ----------------------- */
  const loadBaseline = useCallback(async () => {
    setInvestigation((prev) => ({ ...prev, status: 'loading', error: null }))
    try {
      const invResponse = await fetchInvestigation()
      const invData = invResponse?.investigation ?? invResponse
      setInvestigation({ status: 'ready', data: invData, error: null })

      const [detResponse, cleanData, trajResponse] = await Promise.all([
        fetchDetection(),
        fetchAisCleaning(),
        fetchTrajectories(),
      ])
      const detData = detResponse?.detection ?? detResponse
      setDetection({ status: 'ready', data: detData, error: null })
      setCleaning({ status: 'ready', data: cleanData?.cleaning ?? cleanData, error: null })
      setAis({ status: 'ready', data: trajResponse?.trajectories ?? trajResponse, error: null })

      const candidates = rankingEntries(invData) || []
      if (candidates.length > 0 && !selected) {
        setSelected(candidates[0].mmsi)
      }
    } catch (err) {
      setInvestigation({ status: 'error', data: null, error: String(err.message || err) })
    }
  }, [selected])

  useEffect(() => {
    loadBaseline()
  }, [loadBaseline])

  /* --- Real AIS Loader ------------------------------------------------- */
  // Declared before loadSentinel1, which chains into it once a scene's
  // bounds are known, so the dependency order matches the call order.
  const loadRealAis = useCallback(async (bbox) => {
    setRealAis({ status: 'loading', data: null, error: null })
    try {
      const res = await fetchRealAisAnalyze(bbox ? { bbox } : {})
      setRealAis({ status: 'ready', data: res, error: null })
    } catch (err) {
      setRealAis({ status: 'error', data: null, error: String(err.message || err) })
    }
  }, [])

  /* --- Real Sentinel-1 Loader ------------------------------------------ */
  const loadSentinel1 = useCallback(async () => {
    // `scenePath` is a required field on the service, so an unconfigured build
    // reports why real-data mode is unavailable rather than posting a blank
    // path and surfacing a 422.
    if (!isSentinel1Configured()) {
      setS1Data({
        status: 'error',
        data: null,
        error:
          'No Sentinel-1 scene is configured. Set VITE_SENTINEL1_SCENE_PATH to a local VV+VH GeoTIFF to enable real-data mode.',
      })
      return
    }
    setS1Data({ status: 'loading', data: null, error: null })
    try {
      const res = await fetchSentinel1Detect({
        scenePath: SENTINEL1_SCENE_PATH,
        includePreviews: true,
      })
      setS1Data({ status: 'ready', data: res, error: null })

      // Auto-trigger Real AIS matching against scene bounds
      const bounds = sceneBoundsOf(res)
      if (bounds) {
        loadRealAis(bounds)
      }
    } catch (err) {
      setS1Data({ status: 'error', data: null, error: String(err.message || err) })
    }
  }, [loadRealAis])

  /* --- Real Drift Simulators ------------------------------------------- */
  const handleRunHindcast = useCallback(async () => {
    setDriftLoading(true)
    try {
      const lat = s1Data.data?.result?.centroid?.lat || 22.46282
      const lon = s1Data.data?.result?.centroid?.lon || -93.44692
      const res = await fetchRealDriftSimulate({
        origin_lat: lat,
        origin_lon: lon,
        reference_time_iso: '2024-05-29T00:00:00Z',
        direction: 'backward',
        duration_hours: 6.0,
        step_seconds: 900.0,
      })
      setDriftHindcast(res)
    } catch (err) {
      console.warn('Real drift hindcast failed:', err)
    } finally {
      setDriftLoading(false)
    }
  }, [s1Data.data])

  const handleRunForecast = useCallback(async () => {
    setForecastLoading(true)
    try {
      const lat = s1Data.data?.result?.centroid?.lat || 22.46282
      const lon = s1Data.data?.result?.centroid?.lon || -93.44692
      const res = await fetchRealDriftSimulate({
        origin_lat: lat,
        origin_lon: lon,
        reference_time_iso: '2024-05-29T00:00:00Z',
        direction: 'forward',
        duration_hours: 6.0,
        step_seconds: 900.0,
      })
      setDriftForecast(res)
    } catch (err) {
      console.warn('Real drift forecast failed:', err)
    } finally {
      setForecastLoading(false)
    }
  }, [s1Data.data])

  /* --- Mode switching -------------------------------------------------- */
  const handleSelectDataSource = useCallback(
    (mode) => {
      setViewMode(mode)
      if (mode === 'sentinel1' && s1Data.status === 'idle') {
        loadSentinel1()
      } else if (mode === 'sentinel1' && s1Data.status === 'ready' && realAis.status === 'idle') {
        loadRealAis(sceneBoundsOf(s1Data.data))
      }
    },
    [loadRealAis, loadSentinel1, realAis.status, s1Data.data, s1Data.status],
  )

  const selectedEntry = useMemo(
    () => findCandidate(investigation.data, selected),
    [investigation.data, selected],
  )
  const selectedTrack = useMemo(
    () => findTrajectory(ais.data, selected),
    [ais.data, selected],
  )
  const candidatesList = useMemo(
    () => rankingEntries(investigation.data),
    [investigation.data],
  )

  // `timeline`/`chain` are built inside the Timeline/EvidenceChain panels from
  // the same lib builders, so App keeps no divergent local copy.

  // Stage Navigation controls
  const markStageCompleted = (stageId) => {
    setCompletedStages((prev) => (prev.includes(stageId) ? prev : [...prev, stageId]))
  }

  const navigateToStage = (nextStage) => {
    markStageCompleted(stage)
    setStage(nextStage)
  }

  const handleStartInvestigation = () => {
    setViewState('workspace')
    setStage('detect')
    if (viewMode === 'sentinel1' && s1Data.status !== 'ready') {
      loadSentinel1()
    }
  }

  const handleWhyThisCandidate = (mmsi) => {
    setSelected(mmsi)
    setShowEvidenceChainModal(true)
  }

  /* --- boot screen while the core case is loading ----------------------- */
  if (investigation.status === 'loading' || investigation.status === 'error') {
    if (investigation.status === 'error') {
      return (
        <div className="boot">
          <Card
            title="Could not connect to the ABYSS intelligence service"
            subtitle="The frontend needs the Python service running to compute or fetch CASE-001."
            icon="⚠️"
          >
            <p className="error-text">{investigation.error}</p>
            <button className="btn" onClick={loadBaseline}>Try again</button>
          </Card>
        </div>
      )
    }
    return (
      <div className="boot">
        <Spinner label="Booting ABYSS Maritime Forensic Intelligence Engine..." />
      </div>
    )
  }

  return (
    <div className="app-shell">
      <Header
        activeTab={viewState === 'home' ? 'investigation' : 'workspace'}
        onSelectTab={(tab) => {
          if (tab === 'home') setViewState('home')
          else setViewState('workspace')
        }}
        viewMode={viewMode}
        onSelectViewMode={handleSelectDataSource}
        s1Loading={s1Data.status === 'loading'}
        s1Data={s1Data.data}
      />

      {viewState === 'home' ? (
        <main className="layout" style={{ marginTop: '20px' }}>
          <InvestigationHome
            onStartInvestigation={handleStartInvestigation}
            dataSource={viewMode}
            onSelectDataSource={handleSelectDataSource}
            investigationStatus={investigation.status}
          />
        </main>
      ) : (
        <div className="investigation-workspace">
          {/* Top Persistent Pipeline Navigation */}
          <InvestigationPipelineNav
            currentStage={stage}
            completedStages={completedStages}
            onSelectStage={(s) => setStage(s)}
            onExitToHome={() => setViewState('home')}
          />

          {/* Central Forensic Workspace Grid */}
          <main className="workspace-grid">
            {/* Left / Center: Persistent Geospatial Map */}
            <div className="workspace-map-col">
              <UnifiedMapPanel
                investigation={investigation.data}
                detection={detection.data}
                trajectories={ais.data}
                trajectory={selectedTrack}
                selected={selected}
                onClearSelection={() => setSelected(null)}
                stage={stage}
                driftHindcast={driftHindcast}
                driftForecast={driftForecast}
                s1Data={viewMode === 'sentinel1' ? s1Data.data : null}
                realAis={viewMode === 'sentinel1' ? realAis.data : null}
              />
            </div>

            {/* Right: Stage Detail & Actions */}
            <div className="workspace-stage-col">
              {stage === 'detect' && (
                <DetectionStagePanel
                  isRealMode={viewMode === 'sentinel1'}
                  detection={detection.data}
                  s1Data={s1Data.data}
                  loading={s1Data.status === 'loading'}
                  error={s1Data.error}
                  onRetry={loadSentinel1}
                  realAis={realAis.data}
                  onContinue={() => navigateToStage('origin')}
                />
              )}

              {stage === 'origin' && (
                <OriginReconstructionPanel
                  investigation={investigation.data}
                  onRunHindcast={handleRunHindcast}
                  hindcastLoading={driftLoading}
                  driftHindcast={driftHindcast}
                  onContinue={() => navigateToStage('hindcast')}
                  onPrevious={() => setStage('detect')}
                  isRealMode={viewMode === 'sentinel1'}
                />
              )}

              {stage === 'hindcast' && (
                <HindcastStagePanel
                  investigation={investigation.data}
                  driftHindcast={driftHindcast}
                  onRunHindcast={handleRunHindcast}
                  hindcastLoading={driftLoading}
                  onContinue={() => navigateToStage('forecast')}
                  onPrevious={() => setStage('origin')}
                  isRealMode={viewMode === 'sentinel1'}
                />
              )}

              {stage === 'forecast' && (
                <ForecastStagePanel
                  investigation={investigation.data}
                  driftForecast={driftForecast}
                  onRunForecast={handleRunForecast}
                  forecastLoading={forecastLoading}
                  onContinue={() => navigateToStage('ais')}
                  onPrevious={() => setStage('hindcast')}
                  isRealMode={viewMode === 'sentinel1'}
                />
              )}

              {stage === 'ais' && (
                <div className="stage-panel-ais" style={{ display: 'grid', gap: '20px' }}>
                  {viewMode === 'sentinel1' ? (
                    <RealAisPanel
                      data={realAis.data}
                      loading={realAis.status === 'loading'}
                      error={realAis.error}
                      onRetry={() => loadRealAis(sceneBoundsOf(s1Data.data))}
                      s1Data={s1Data.data}
                    />
                  ) : (
                    <>
                      <CandidateTable
                        investigation={investigation.data}
                        selected={selected}
                        onSelect={(mmsi) => setSelected(String(selected) === String(mmsi) ? null : mmsi)}
                      />
                      {selectedEntry && (
                        <CandidateDetail
                          candidate={selectedEntry}
                          trajectory={selectedTrack}
                          weights={investigation.data?.weights}
                        />
                      )}
                    </>
                  )}
                  <div className="stage-actions" style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <button type="button" className="btn btn-ghost" onClick={() => setStage('forecast')}>
                      ← PREVIOUS
                    </button>
                    <button type="button" className="btn btn-primary" onClick={() => navigateToStage('behaviour')}>
                      CONTINUE TO BEHAVIOUR →
                    </button>
                  </div>
                </div>
              )}

              {stage === 'behaviour' && (
                <BehaviourStagePanel
                  investigation={investigation.data}
                  selected={selected}
                  trajectory={selectedTrack}
                  candidate={selectedEntry}
                  onContinue={() => navigateToStage('evidence')}
                  onPrevious={() => setStage('ais')}
                  isRealMode={viewMode === 'sentinel1'}
                  realAis={realAis.data}
                />
              )}

              {stage === 'evidence' && (
                <EvidenceFusionPanel
                  investigation={investigation.data}
                  detection={detection.data}
                  s1Data={viewMode === 'sentinel1' ? s1Data.data : null}
                  candidates={candidatesList}
                  selected={selected}
                  onSelectCandidate={(mmsi) => setSelected(mmsi)}
                  onWhyThisCandidate={handleWhyThisCandidate}
                  onContinue={() => navigateToStage('review')}
                  onPrevious={() => setStage('behaviour')}
                  isRealMode={viewMode === 'sentinel1'}
                  realAis={realAis.data}
                />
              )}

              {stage === 'review' && (
                <InvestigatorReviewPanel
                  investigation={investigation.data}
                  detection={detection.data}
                  s1Data={viewMode === 'sentinel1' ? s1Data.data : null}
                  selected={selected}
                  candidate={selectedEntry}
                  onViewEvidenceChain={() => setShowEvidenceChainModal(true)}
                  onPrevious={() => setStage('evidence')}
                  isRealMode={viewMode === 'sentinel1'}
                  realAis={realAis.data}
                />
              )}
            </div>

            {/* Bottom: Event Timeline & Persistent Evidence Chain Anchor */}
            <div className="workspace-bottom-col">
              <Timeline
                investigation={investigation.data}
                detection={detection.data}
                selected={selected}
                onSelect={(mmsi) => setSelected(String(mmsi))}
              />

              {(showEvidenceChainModal || stage === 'evidence' || stage === 'review') && (
                <div id="evidence-chain-anchor" style={{ marginTop: '20px' }}>
                  <EvidenceChain
                    investigation={investigation.data}
                    detection={detection.data}
                    selected={selected}
                    trajectory={selectedTrack}
                    onSelect={(mmsi) => setSelected(String(mmsi))}
                  />
                </div>
              )}
            </div>
          </main>
        </div>
      )}
    </div>
  )
}
