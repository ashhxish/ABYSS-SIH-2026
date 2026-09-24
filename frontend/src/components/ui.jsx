/** Small building blocks shared by every panel. */

/** A titled panel. `id` is used by the workflow stepper to scroll to it. */
export function Card({ id, title, subtitle, icon, actions, children, className = '' }) {
  return (
    <section id={id} className={`card ${className}`.trim()}>
      <header className="card-head">
        <div className="card-title">
          {icon ? <span className="card-icon" aria-hidden="true">{icon}</span> : null}
          <div>
            <h2>{title}</h2>
            {subtitle ? <p className="card-sub">{subtitle}</p> : null}
          </div>
        </div>
        {actions ? <div className="card-actions">{actions}</div> : null}
      </header>
      <div className="card-body">{children}</div>
    </section>
  )
}

/** Label/value row. `mono` is for identifiers such as MMSI or coordinates. */
export function Row({ label, value, mono = false, hint }) {
  return (
    <div className="row">
      <span className="row-label" title={hint}>
        {label}
      </span>
      <span className={mono ? 'row-value mono' : 'row-value'}>{value ?? '—'}</span>
    </div>
  )
}

export function Badge({ tone = 'neutral', children, title }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  )
}

export function Stat({ label, value, sub, tone = 'neutral' }) {
  return (
    <div className={`stat stat-${tone}`}>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
      {sub ? <span className="stat-sub">{sub}</span> : null}
    </div>
  )
}

/** Horizontal bar used for scores and factor contributions. */
export function Bar({ percent, tone = 'accent', label }) {
  const pct = Math.max(0, Math.min(1, Number(percent) || 0)) * 100
  return (
    <div
      className="bar"
      role="img"
      aria-label={label || `${pct.toFixed(0)}%`}
      title={label || `${pct.toFixed(0)}%`}
    >
      <div className={`bar-fill bar-${tone}`} style={{ width: `${pct.toFixed(1)}%` }} />
    </div>
  )
}

/** Circular confidence gauge (SVG, no dependency). */
export function Gauge({ value, label, caption, size = 116 }) {
  const frac = Math.max(0, Math.min(1, Number(value) || 0))
  const stroke = 10
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  return (
    <div className="gauge">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
           aria-label={`${label} ${Math.round(frac * 100)} percent`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${(c * frac).toFixed(2)} ${c.toFixed(2)}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text x="50%" y="47%" textAnchor="middle" className="gauge-value">
          {`${Math.round(frac * 100)}%`}
        </text>
        <text x="50%" y="64%" textAnchor="middle" className="gauge-caption">
          {caption || label}
        </text>
      </svg>
    </div>
  )
}

/** Bulleted caution/limitations list from the API. */
export function NoticeList({ title, items, tone = 'warn' }) {
  const list = Array.isArray(items) ? items.filter(Boolean) : []
  if (list.length === 0) return null
  return (
    <div className={`notice notice-${tone}`}>
      {title ? <strong>{title}</strong> : null}
      <ul>
        {list.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  )
}

export function Spinner({ label = 'Loading' }) {
  return (
    <div className="spinner" role="status">
      <span className="spinner-dot" />
      <span>{label}</span>
    </div>
  )
}

export function Empty({ children }) {
  return <p className="empty">{children}</p>
}
