export const LANGUAGES = [
  { code: 'en', label: 'English', native: 'English' },
  { code: 'hi', label: 'Hindi', native: 'हिन्दी' },
  { code: 'te', label: 'Telugu', native: 'తెలుగు' },
]
export const languageName = (code) => LANGUAGES.find((l) => l.code === code)?.label || (code ? code : 'Unknown')

export function formatBytes(n) {
  if (n == null) return '-'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export function formatDate(iso, withTime = false) {
  if (!iso) return '-'
  const opts = withTime ? { dateStyle: 'medium', timeStyle: 'short' } : { dateStyle: 'medium' }
  return new Intl.DateTimeFormat(undefined, opts).format(new Date(iso))
}

export function timeAgo(iso) {
  if (!iso) return ''
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`
  return formatDate(iso)
}

export const MODES = [
  { value: 'hybrid', label: 'Hybrid', hint: 'Meaning + exact words (recommended)' },
  { value: 'vector', label: 'Meaning only', hint: 'Semantic search baseline' },
  { value: 'bm25', label: 'Exact words only', hint: 'Keyword search' },
  { value: 'hybrid_rerank', label: 'Hybrid + reranker', hint: 'Slower, needs the reranker model on the server' },
]
export const modeLabel = (v) => MODES.find((m) => m.value === v)?.label || v

export const STAGE_LABELS = {
  started: 'Starting',
  rewriting: 'Understanding your follow-up',
  retrieving: 'Searching your documents',
  generating: 'Writing the answer',
  verifying: 'Checking every source',
}

export const pct = (x) => (x == null ? '-' : `${(x * 100).toFixed(1)}%`)
