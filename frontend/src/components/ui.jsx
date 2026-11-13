import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'

export function Spinner({ label }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted" role="status">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      {label || <span className="sr-only">Loading</span>}
    </span>
  )
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="font-display text-3xl font-bold leading-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}

/** A titled block separated by a rule instead of a card, so page hierarchy comes from spacing and lines. */
export function Section({ title, hint, action, children, className = '' }) {
  return (
    <section className={`border-t border-line pt-5 ${className}`}>
      {(title || action) && (
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            {title && <h2 className="font-display text-lg font-bold">{title}</h2>}
            {hint && <p className="text-sm text-muted">{hint}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function Field({ label, hint, error, children, htmlFor }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium">{label}</label>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {error && <p className="mt-1 text-xs text-bad" role="alert">{error}</p>}
    </div>
  )
}

export function ErrorNote({ children, onRetry }) {
  if (!children) return null
  return (
    <div className="flex items-start gap-2 rounded-field border border-bad/40 bg-bad/10 px-3 py-2 text-sm text-bad" role="alert">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="flex-1">{children}</span>
      {onRetry && <button className="font-medium underline" onClick={onRetry}>Try again</button>}
    </div>
  )
}

export function Notice({ tone = 'ok', children }) {
  const cls = tone === 'ok' ? 'border-ok/40 bg-ok/10 text-ok' : 'border-warn/40 bg-warn/10 text-warn'
  return (
    <div className={`flex items-start gap-2 rounded-field border px-3 py-2 text-sm ${cls}`} role="status">
      {tone === 'ok' ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" /> : <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />}
      <span>{children}</span>
    </div>
  )
}

export function EmptyState({ icon: Icon, title, children, action }) {
  return (
    <div className="flex flex-col items-start gap-2 border-t border-dashed border-line py-10">
      {Icon && <Icon className="h-7 w-7 text-muted" aria-hidden="true" />}
      <h3 className="font-display text-lg font-bold">{title}</h3>
      {children && <p className="max-w-md text-sm text-muted">{children}</p>}
      {action}
    </div>
  )
}

const STATUS = {
  ready: ['Ready', 'text-ok bg-ok/10 border-ok/30'],
  processing: ['Processing', 'text-warn bg-warn/10 border-warn/30'],
  pending: ['Queued', 'text-muted bg-line/50 border-line'],
  failed: ['Failed', 'text-bad bg-bad/10 border-bad/30'],
}
export function StatusBadge({ status }) {
  const [label, cls] = STATUS[status] || [status, 'text-muted border-line']
  return <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${cls}`}>{label}</span>
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div role="tablist" className="mb-6 flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={value === t.value}
          onClick={() => onChange(t.value)}
          className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
            value === t.value ? 'border-brand text-brand' : 'border-transparent text-muted hover:text-ink'}`}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function Figure({ label, value, note }) {
  return (
    <div className="min-w-[8rem]">
      <div className="font-display text-3xl font-bold tabular-nums">{value}</div>
      <div className="text-sm font-medium">{label}</div>
      {note && <div className="text-xs text-muted">{note}</div>}
    </div>
  )
}

export function Pagination({ total, limit, offset, onChange }) {
  if (total <= limit) return null
  const page = Math.floor(offset / limit) + 1
  const pages = Math.ceil(total / limit)
  return (
    <nav className="mt-4 flex items-center justify-between text-sm" aria-label="Pagination">
      <span className="text-muted">Page {page} of {pages}</span>
      <div className="flex gap-2">
        <button className="btn btn-quiet" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
        <button className="btn btn-quiet" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</button>
      </div>
    </nav>
  )
}
