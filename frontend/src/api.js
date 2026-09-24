/**
 * Minimal API client for the Phase 13 ABYSS intelligence service.
 *
 * Every value rendered by the console comes from these calls - the UI invents
 * no numbers of its own. Each helper returns the parsed JSON body and throws an
 * ApiError carrying the HTTP status plus the server's `detail` message, so the
 * UI can show what actually failed instead of a generic "something went wrong".
 */
const BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

const DEFAULT_TIMEOUT_MS = 30000

export class ApiError extends Error {
  constructor(message, { status = 0, path = '', cause } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.path = path
    if (cause) this.cause = cause
  }

  /** True when the backend answered, i.e. the failure is a server-side 4xx/5xx. */
  get isServerError() {
    return this.status >= 500
  }

  /** True when we never reached the backend (not running, wrong port, timeout). */
  get isUnreachable() {
    return this.status === 0
  }
}

async function extractDetail(response) {
  try {
    const body = await response.json()
    if (body && typeof body.detail === 'string') return body.detail
    if (body && Array.isArray(body.detail)) {
      // FastAPI validation errors
      return body.detail
        .map((d) => `${(d.loc || []).join('.')}: ${d.msg}`)
        .join('; ')
    }
    if (body && typeof body === 'object' && body.message) return body.message
  } catch {
    /* response had no JSON body - fall through to the status text */
  }
  return null
}

async function request(path, { method = 'GET', body, signal, timeoutMs } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs ?? DEFAULT_TIMEOUT_MS)

  // Allow a caller-supplied signal (e.g. unmount) to cancel the request too.
  const onAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onAbort, { once: true })
  }

  try {
    const response = await fetch(`${BASE}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })

    if (!response.ok) {
      const detail = await extractDetail(response)
      throw new ApiError(
        detail
          ? `${response.status} ${response.statusText}: ${detail}`
          : `${response.status} ${response.statusText}`,
        { status: response.status, path },
      )
    }
    return await response.json()
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err.name === 'AbortError') {
      throw new ApiError(
        signal?.aborted
          ? 'Request cancelled.'
          : `Request to ${path} timed out after ${(timeoutMs ?? DEFAULT_TIMEOUT_MS) / 1000}s.`,
        { status: 0, path, cause: err },
      )
    }
    throw new ApiError(
      `Cannot reach the intelligence service at ${BASE}${path} (${err.message}). ` +
        'Is it running? Start it with: uvicorn app.main:app --port 8000',
      { status: 0, path, cause: err },
    )
  } finally {
    clearTimeout(timer)
    if (signal) signal.removeEventListener('abort', onAbort)
  }
}

const get = (path, opts) => request(path, { ...opts, method: 'GET' })
const post = (path, body, opts) => request(path, { ...opts, method: 'POST', body: body ?? {} })

/* ---------------------------------------------------------------- endpoints */

/** Service liveness + which demo bundle is mounted. */
export const fetchHealth = (opts) => get('/health', opts)

/** End-to-end CASE-001 investigation: origin region, ranking, per-vessel evidence. */
export const fetchInvestigation = (body, opts) => post('/investigate', body, opts)

/** Ranking only, with optional evidence-weight overrides. */
export const fetchScore = (body, opts) => post('/score', body, opts)

/** Satellite observation: detection verdict, confidence, polygon characterisation. */
export const fetchDetection = (opts) => post('/detect', opts)

/** AIS cleaning audit (records omitted: this console never needs raw rows). */
export const fetchAisCleaning = (opts) => post('/ais/clean', { includeRecords: false }, opts)

/** Reconstructed AIS trajectories. Large payload (~2 MB) - load it lazily. */
export const fetchTrajectories = (opts) => post('/ais/trajectory', opts)

/** Free-text description of the mounted data sources. */
export const fetchDataSources = (opts) => get('/data-sources', opts)
