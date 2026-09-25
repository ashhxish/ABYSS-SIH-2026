/**
 * Phase 18 - automated forensic investigation report.
 *
 * Renders the document produced by `lib/report.js`. That module is a pure
 * formatter over payloads the console already holds, so this view adds no
 * analysis of its own: it only lays out sections, shows each value with the
 * API path it came from, and honours the selected candidate.
 *
 * "Generate Investigation Report" builds the document from state already in
 * memory - it issues no API request of its own.
 */
import { useMemo, useState } from 'react'
import { buildInvestigationReport, REPORT_DISCLAIMER, SCORE_LABEL, STATUS } from '../lib/report.js'
import { Badge, Card, Empty } from './ui.jsx'

/** Renders one `fact()` object from the report builder. */
function Fact({ item, compact = false }) {
  if (!item) return null
  return (
    <div className={`rep-fact${item.available ? '' : ' is-unavailable'}${compact ? ' rep-fact-compact' : ''}`}>
      <dt>{item.label}</dt>
      <dd>
        <span className="rep-fact-value">{item.display}</span>
        {item.available ? null : <span className="rep-fact-why">{item.unavailable}</span>}
        <span className="rep-source mono" title="API field this value was read from">
          {item.source}
        </span>
      </dd>
    </div>
  )
}

/** The `fact()` objects in a data object, in their declared order. */
function Facts({ items, compact = false }) {
  const facts = (items || []).filter((item) => item && item.label)
  if (!facts.length) return null
  return (
    <dl className="rep-facts">
      {facts.map((item) => (
        <Fact key={`${item.label}-${item.source}`} item={item} compact={compact} />
      ))}
    </dl>
  )
}

/** A provenance footnote. */
function Source({ children }) {
  if (!children) return null
  return <p className="rep-source mono">Source: {children}</p>
}

/** A titled report block that states why it is missing instead of rendering nothing. */
function RepSection({ id, section, number, children }) {
  if (!section) return null
  if (!section.available) {
    return (
      <section className="rep-section is-unavailable" id={`rep-${id}`}>
        <h3>
          <span className="rep-num">{number}</span>
          {section.title}
          <Badge tone="muted">Unavailable</Badge>
        </h3>
        <p className="rep-unavailable-note">{section.unavailableReason || 'Not provided by the API response.'}</p>
      </section>
    )
  }
  return (
    <section className="rep-section" id={`rep-${id}`}>
      <h3>
        <span className="rep-num">{number}</span>
        {section.title}
      </h3>
      {children ? children(section.data) : null}
    </section>
  )
}

/** A note/bulleted list, rendered only when the source supplied entries. */
function Notes({ title, items, tone = 'neutral' }) {
  const entries = (items || []).filter(Boolean)
  if (!entries.length) return null
  return (
    <div className={`rep-notes rep-notes-${tone}`}>
      {title ? <h5 className="rep-sub">{title}</h5> : null}
      <ul className="rep-list">
        {entries.map((item, i) => (
          <li key={`${item}-${i}`}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

/** The investigation-status line for section 1, with the basis the API implied. */
function StatusBox({ status }) {
  if (!status) return null
  return (
    <div className="rep-status">
      <Badge tone={status.value === STATUS.EMPTY ? 'warn' : 'ok'}>{status.value}</Badge>
      {status.basis ? <span className="fine-print">{status.basis}</span> : null}
    </div>
  )
}

export default function InvestigationReport({ investigation, detection, cleaning, timeline, chain, selected }) {
  const [generated, setGenerated] = useState(false)

  const report = useMemo(
    () =>
      buildInvestigationReport({
        investigation,
        detection,
        cleaning,
        timeline,
        chain,
        selectedMmsi: selected,
      }),
    [investigation, detection, cleaning, timeline, chain, selected],
  )

  if (!investigation) return null

  const status =
    Object.values(report.generatedFrom).every(Boolean) ? STATUS.COMPLETE : STATUS.PARTIAL
  const sections = report.sections.filter((section) => section.available && section.data)

  return (
    <Card
      id="report"
      title="Automated forensic investigation report"
      subtitle="Every value is reproduced from the API response, the Phase 16 timeline and the Phase 17 evidence chain"
      icon="📄"
      className="card-report"
      actions={
        <>
          <Badge tone="accent">{report.reportId}</Badge>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setGenerated(true)}
            disabled={!sections.length}
          >
            {generated ? 'Report generated' : 'Generate Investigation Report'}
          </button>
          {generated ? (
            <>
              <button type="button" className="btn" onClick={() => window.print()}>
                Print / save as PDF
              </button>
              <button type="button" className="btn" onClick={() => setGenerated(false)}>
                Hide
              </button>
            </>
          ) : null}
        </>
      }
    >
      <p className="rep-intro">
        This report presents evidence compatibility and investigation priority generated by the ABYSS
        prototype. It does not establish legal responsibility or causation.
      </p>

      {!generated ? (
        <Empty>
          Press <strong>Generate Investigation Report</strong> to build the document for the
          currently selected candidate. It is assembled from data already loaded in this console - no
          further requests are made.
        </Empty>
      ) : null}
      {generated ? (
        <article className="rep-doc" data-testid="report-document">
          <header className="rep-cover">
            <div className="rep-cover-mark">ABYSS</div>
            <div>
              <p className="rep-cover-kicker">Maritime forensic investigation support system</p>
              <h3 className="rep-cover-title">Investigation report {report.caseId}</h3>
              <p className="rep-cover-sub">
                Candidate {report.selectedVesselId || '—'} · MMSI {report.selectedMmsi || '—'} ·
                rank {report.selectedRank == null ? '—' : `#${report.selectedRank}`}
              </p>
            </div>
            <div className="rep-cover-status">
              <Badge tone="demo">{status}</Badge>
              <Badge tone="warn">synthetic demonstration AIS</Badge>
            </div>
          </header>

          <div className="rep-toc">
            {sections.map((section) => (
              <a key={section.id} href={`#rep-${section.id}`}>
                {section.title}
              </a>
            ))}
          </div>

          {/* 1 */}
          <RepSection id="case" section={report.sections.find((s) => s.id === 'case')} number={1}>
            {(data) => (
              <>
                <Facts
                  items={[
                    data.caseId,
                    data.observationTime,
                    data.acquisitionTime,
                    data.datasetLabel,
                    data.synthetic,
                    data.mode,
                  ].filter(Boolean)}
                />
                <StatusBox status={data.status} />
              </>
            )}
          </RepSection>

          {/* 2 + 3 */}
          <div className="rep-two-col">
            <RepSection
              id="observation"
              section={report.sections.find((s) => s.id === 'observation')}
              number={2}
            >
              {(data) => (
                <>
                  <Facts
                    items={[
                      data.acquisitionTime,
                      data.detectionConfidence,
                      data.centroidLat,
                      data.centroidLon,
                      data.areaKm2,
                    ].filter(Boolean)}
                  />
                  <Facts compact items={data.geometryFacts} />
                  <Source>{data.source}</Source>
                </>
              )}
            </RepSection>
            <RepSection
              id="look-alike"
              section={report.sections.find((s) => s.id === 'look-alike')}
              number={3}
            >
              {(data) => (
                <>
                  <Facts
                    items={[
                      data.result,
                      data.lowWindArea,
                      data.windSpeedMs,
                      data.thresholdMs,
                    ].filter(Boolean)}
                  />
                  {data.flags?.length ? (
                    <ul className="rep-list">
                      {data.flags.map((flag, i) => (
                        <li key={`${flag}-${i}`}>{flag}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="fine-print">No look-alike indicator was raised by the screening heuristics.</p>
                  )}
                  <p className="rep-caveat">{data.heuristicNote}</p>
                  <Source>{data.source}</Source>
                </>
              )}
            </RepSection>
          </div>
          {/* 4 + 5 */}
          <div className="rep-two-col">
            <RepSection id="origin" section={report.sections.find((s) => s.id === 'origin')} number={4}>
              {(data) => (
                <>
                  <p className="rep-model-tag">MODELLED / INFERRED — not observed evidence</p>
                  <Facts
                    items={[
                      data.regionConfidence,
                      data.areaKm2,
                      data.windowStart,
                      data.windowEnd,
                      data.windowDuration,
                    ].filter(Boolean)}
                  />
                  <Source>{data.source}</Source>
                </>
              )}
            </RepSection>
            <RepSection
              id="environment"
              section={report.sections.find((s) => s.id === 'environment')}
              number={5}
            >
              {(data) => (
                <>
                  <Facts
                    items={[
                      data.datasetLabel,
                      data.timeBehaviour,
                      data.windageCoefficient,
                      data.stepSeconds,
                      data.sampleHours,
                      data.regionBufferKm,
                      data.prototypeParameters,
                    ].filter(Boolean)}
                  />
                  <p className="rep-caveat">
                    Environmental values are read from the provider bundle the API returned. No
                    measurement is re-derived, estimated or supplied by this report.
                  </p>
                  <Source>{data.source}</Source>
                </>
              )}
            </RepSection>
          </div>

          {/* 6 */}
          <RepSection id="ais" section={report.sections.find((s) => s.id === 'ais')} number={6}>
            {(data) => (
              <>
                <Facts
                  items={[
                    data.datasetLabel,
                    data.recordsRetained,
                    data.removedValues,
                    data.vesselsScored,
                    data.insideRegionDuringWindow,
                    data.behaviourAnomaliesReported,
                    data.tieGroupCount,
                  ].filter(Boolean)}
                />
                <Source>{data.source}</Source>
              </>
            )}
          </RepSection>

          {/* 7 */}
          <RepSection
            id="candidate"
            section={report.sections.find((s) => s.id === 'candidate')}
            number={7}
          >
            {(data) => (
              <>
                <div className="rep-candidate-head">
                  <div>
                    <h4>{data.name?.value || '—'}</h4>
                    <p className="mono">
                      {data.vesselId?.value || '—'} · MMSI {data.mmsi?.value || '—'}
                    </p>
                  </div>
                  <div className="rep-candidate-score">
                    <strong>{data.totalScore?.display || '—'}</strong>
                    <span>{report.scoreLabel}</span>
                  </div>
                </div>
                <Facts
                  items={[data.vesselType, data.rank, data.distanceToSlickKm].filter(Boolean)}
                  compact
                />
                {data.passedFilters?.available ? (
                  <p className="fine-print">
                    Passed every compatibility filter:{' '}
                    {Object.entries(data.passedFilters.value)
                      .map(([key, value]) => `${key}=${value ? 'yes' : 'no'}`)
                      .join(' · ')}{' '}
                    <span className="mono rep-source">{data.passedFilters.source}</span>
                  </p>
                ) : null}
                <h5 className="rep-sub">Evidence factors</h5>
                <table className="rep-table">
                  <thead>
                    <tr>
                      <th>Factor</th>
                      <th>Points</th>
                      <th>Cap</th>
                      <th>Share</th>
                      <th>Provenance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.factors || []).map((factor) => (
                      <tr key={factor.key}>
                        <th scope="row">{factor.label}</th>
                        <td className="mono">{factor.display}</td>
                        <td className="mono">{factor.maxDisplay}</td>
                        <td className="mono">{factor.shareDisplay}</td>
                        <td className="mono rep-td-src">{factor.source}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <h5 className="rep-sub">Engine reasons (unmodified)</h5>
                <ul className="rep-list rep-reasons">
                  {(data.reasons || []).map((reason, i) => (
                    <li key={`${reason}-${i}`}>{reason}</li>
                  ))}
                </ul>
                <Source>{data.reasonsSource}</Source>
                <h5 className="rep-sub">Compatibility detail</h5>
                <Facts items={Object.values(data.compatibility || {})} compact />
                <Source>{data.compatibility?.minDistanceKmDuringWindow?.source}</Source>

                <h5 className="rep-sub">Behavioural evidence</h5>
                {data.behaviour?.available ? (
                  <>
                    <Facts
                      items={[
                        data.behaviour.description,
                        data.behaviour.isAnomaly,
                        data.behaviour.rawAnomaly,
                        data.behaviour.scoredEligible,
                        data.behaviour.baselineMedianSog,
                        data.behaviour.windowMedianSog,
                      ].filter(Boolean)}
                      compact
                    />
                    {data.behaviour.events?.length ? (
                      <ul className="rep-list rep-events">
                        {data.behaviour.events.map((event) => (
                          <li key={event.id}>
                            <span className="rep-event-title">{event.title}</span>
                            {event.at ? <span className="mono rep-event-at"> · {event.at}</span> : null}
                            <Badge tone="muted">{event.status}</Badge>
                            <span className="rep-event-desc">{event.description}</span>
                            {event.metrics?.length ? (
                              <span className="rep-event-metrics mono">
                                {event.metrics.map((m) => `${m.label}: ${m.value}`).join(' · ')}
                              </span>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="rep-unavailable-note">
                        The timeline produced no timestamped behaviour event for this vessel; the anomaly summary above is
                        the engine's own.
                      </p>
                    )}
                    <Notes title="How the anomaly is computed" items={data.behaviour.notes} />
                    {data.behaviour.note ? <p className="fine-print">{data.behaviour.note}</p> : null}
                    <Source>{data.behaviour.eventsSource}</Source>
                  </>
                ) : (
                  <p className="rep-unavailable-note">No behaviour assessment was returned for this vessel.</p>
                )}

                <h5 className="rep-sub">AIS gap evidence (contextual only)</h5>
                {data.gaps?.available ? (
                  <>
                    <table className="rep-table">
                      <thead>
                        <tr>
                          <th>Gap</th>
                          <th>Duration</th>
                          <th>Straight line</th>
                          <th>Implied speed</th>
                          <th>Feasibility</th>
                          <th>Window overlap</th>
                          <th>Relevance</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(data.gaps.items || []).map((gap, i) => (
                          <tr key={`${gap.start}-${i}`}>
                            <th scope="row" className="mono">
                              {gap.start} → {gap.end}
                            </th>
                            <td className="mono">{fmtGap(gap.durationHours, 'h')}</td>
                            <td className="mono">{fmtGap(gap.straightLineKm, 'km')}</td>
                            <td className="mono">{fmtGap(gap.impliedSpeedKn, 'kn')}</td>
                            <td>
                              <Badge tone={gap.feasible ? 'ok' : 'warn'}>
                                {gap.feasible ? 'Physically feasible' : 'Physically incompatible'}
                              </Badge>
                            </td>
                            <td>{gap.overlapsWindow ? 'Yes' : 'No'}</td>
                            <td className="mono">{fmtGap(gap.relevance, '')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {(data.gaps.items || []).map((gap, i) =>
                      gap.reasons?.length ? (
                        <ul className="rep-list rep-reasons" key={`gap-reasons-${i}`}>
                          {gap.reasons.map((reason, j) => (
                            <li key={`${reason}-${j}`}>{reason}</li>
                          ))}
                        </ul>
                      ) : null
                    )}
                    <Notes title="Gap notes" items={data.gaps.notes} />
                    <p className="fine-print warn-text">{data.gaps.contextNote}</p>
                    <Source>{data.gaps.source}</Source>
                  </>
                ) : (
                  <>
                    <p className="rep-unavailable-note">
                      No AIS transmission gap was recorded for this vessel. The absence of a gap is not evidence either.
                    </p>
                    <p className="fine-print warn-text">{data.gaps?.contextNote}</p>
                  </>
                )}

                <h5 className="rep-sub">Counterfactual comparison</h5>
                {data.counterfactual?.available ? (
                  <blockquote className="rep-counterfactual">
                    {data.counterfactual.text?.value}
                    {data.counterfactual.againstName?.value ? (
                      <footer>Compared with {data.counterfactual.againstName.value}</footer>
                    ) : null}
                    <Source>{data.counterfactual.source}</Source>
                  </blockquote>
                ) : (
                  <p className="rep-unavailable-note">
                    Counterfactual comparison unavailable — the engine returned no comparison for this vessel.
                  </p>
                )}
              </>
            )}
          </RepSection>
          {/* 8 */}
          <RepSection
            id="timeline"
            section={report.sections.find((s) => s.id === 'timeline')}
            number={8}
          >
            {(data) => (
              <>
                <p className="rep-lede">
                  {data.counts?.case ?? 0} case events and {data.counts?.vessel ?? 0} events for the selected vessel,
                  rebuilt by the Phase 16 timeline builder from the same investigation payload.
                </p>
                <div className="rep-tl-summary">
                  {(data.byStatus || []).map((row) => (
                    <span key={row.status} className="rep-tl-chip">
                      <Badge tone="muted">{row.status}</Badge>
                      <strong>{row.count}</strong>
                    </span>
                  ))}
                </div>
                {data.range ? (
                  <p className="fine-print">
                    Timeline span {data.range.start} → {data.range.end}
                  </p>
                ) : null}
                <h5 className="rep-sub">Case events</h5>
                <ol className="rep-list rep-timeline">
                  {(data.caseEvents || []).map((event) => (
                    <li key={event.id}>
                      <span className="mono rep-event-at">{event.at || '—'}</span>
                      <span className="rep-event-title">{event.title}</span>
                      <Badge tone="muted">{event.status}</Badge>
                      <span className="rep-event-desc">{event.description}</span>
                    </li>
                  ))}
                </ol>
                <h5 className="rep-sub">Selected-vessel events</h5>
                {(data.vesselEvents || []).length ? (
                  <ul className="rep-list rep-timeline">
                    {data.vesselEvents.map((event) => (
                      <li key={event.id}>
                        <span className="mono rep-event-at">{event.at || '—'}</span>
                        <span className="rep-event-title">{event.title}</span>
                        <Badge tone="muted">{event.status}</Badge>
                        <span className="rep-event-desc">{event.description}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="rep-unavailable-note">
                    The timeline produced no events for the selected vessel.
                  </p>
                )}
                <Source>{data.source}</Source>
              </>
            )}
          </RepSection>

          {/* 9 */}
          <RepSection
            id="chain"
            section={report.sections.find((s) => s.id === 'chain')}
            number={9}
          >
            {(data) => (
              <>
                <p className="rep-lede">
                  {data.nodeCount} evidence nodes across {data.layerCount} layers, {data.edgeCount} traced links. Same
                  graph as the console's evidence chain.
                </p>
                <table className="rep-table">
                  <thead>
                    <tr>
                      <th>Layer</th>
                      <th>Nodes</th>
                      <th>Provenance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.layers || []).map((layer) => (
                      <tr key={layer.id}>
                        <th scope="row">
                          {layer.title}
                          {layer.caption ? <span className="rep-layer-caption"> · {layer.caption}</span> : null}
                        </th>
                        <td className="mono">
                          {(layer.nodes || []).map((node) => node.title).join(', ')}
                        </td>
                        <td className="mono rep-td-src">
                          {(layer.nodes || []).map((node) => node.source).filter(Boolean).join(', ')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Notes title="Chain note" items={data.notes} />
                <Source>{data.source}</Source>
              </>
            )}
          </RepSection>
          {/* 10 */}
          <RepSection
            id="confidence"
            section={report.sections.find((s) => s.id === 'confidence')}
            number={10}
          >
            {(data) => (
              <>
                <p className="rep-lede">
                  Confidence dimensions are reported separately and are never combined into a single number.
                </p>
                <table className="rep-table rep-conf-table">
                  <thead>
                    <tr>
                      <th>Dimension</th>
                      <th>Value</th>
                      <th>Basis</th>
                      <th>Provenance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.dimensions || []).map((dim) => (
                      <tr key={dim.key} className={dim.available ? '' : 'is-unavailable'}>
                        <th scope="row">
                          {dim.label}
                          {dim.statusLabel ? <Badge tone="muted">{dim.statusLabel}</Badge> : null}
                        </th>
                        <td className="mono">{dim.display}</td>
                        <td>{dim.basis || '—'}</td>
                        <td className="mono rep-td-src">{dim.source || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Notes title="Confidence notes" items={data.notes} tone="warn" />
                <Source>{data.source}</Source>
              </>
            )}
          </RepSection>

          {/* 11 */}
          <RepSection
            id="limitations"
            section={report.sections.find((s) => s.id === 'limitations')}
            number={11}
          >
            {(data) => (
              <>
                <ul className="rep-list rep-limitations">
                  {(data.items || []).map((item, i) => (
                    <li key={`${item}-${i}`}>{item}</li>
                  ))}
                </ul>
                <Source>{data.source}</Source>
              </>
            )}
          </RepSection>

          {/* 12 */}
          <RepSection
            id="methodology"
            section={report.sections.find((s) => s.id === 'methodology')}
            number={12}
          >
            {(data) => (
              <>
                <blockquote className="rep-disclaimer">{data.disclaimer}</blockquote>
                <Facts items={data.weights || []} compact />
                <Notes title="Method notes" items={data.notes} />
                <p className="fine-print">
                  Terminology in this report: <em>candidate vessel</em>, <em>evidence compatibility</em>,{' '}
                  <em>candidate ranking</em>, <em>probable origin</em>, <em>uncertainty region</em>,{' '}
                  <em>investigation confidence</em>. The report does not attribute legal responsibility or causation to
                  any vessel.
                </p>
                <Source>{data.source}</Source>
              </>
            )}
          </RepSection>
        </article>
      ) : null}

      {!generated ? (
        <Empty>
          Press <strong>Generate Investigation Report</strong> to produce the investigator-facing document from the
          investigation currently loaded. The report is built in the browser from this console&rsquo;s existing API data
          — it issues no additional request.
        </Empty>
      ) : null}
    </Card>
  )
}

/** Formats one gap value, or an explicit dash when the API did not supply it. */
function fmtGap(value, unit) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  const rounded = Math.round(value * 100) / 100
  return unit ? `${rounded} ${unit}` : String(rounded)
}

