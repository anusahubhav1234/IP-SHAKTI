import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { History as HistoryIcon, Trash2 } from 'lucide-react'
import { PageBody } from '../layouts/AppLayout'
import { EmptyState, ErrorNote, PageHeader, Pagination, Spinner } from '../components/ui'
import { chatApi, errorMessage } from '../services/api'
import { formatDate, timeAgo } from '../utils/format'

const LIMIT = 20

export default function History() {
  const [data, setData] = useState(null)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')
  const load = useCallback(() => chatApi.conversations({ limit: LIMIT, offset }).then((r) => { setData(r); setError('') }).catch((e) => setError(errorMessage(e))), [offset])
  useEffect(() => { load() }, [load])

  async function remove(c) {
    if (!window.confirm(`Delete “${c.title}”?`)) return
    await chatApi.removeConversation(c.id).catch((e) => setError(errorMessage(e)))
    load()
  }
  const items = (data?.items || []).filter((c) => c.title.toLowerCase().includes(q.toLowerCase()))

  return (
    <PageBody>
      <PageHeader title="History" subtitle="Your past conversations. Only titles are filtered here." />
      <input className="field mb-4" aria-label="Filter conversations by title" placeholder="Filter this page by title" value={q} onChange={(e) => setQ(e.target.value)} />
      <ErrorNote onRetry={load}>{error}</ErrorNote>
      {!data ? <Spinner label="Loading history" /> : items.length === 0 ? (
        <EmptyState icon={HistoryIcon} title={q ? 'No match on this page' : 'No conversations yet'} action={!q && <Link className="btn btn-primary mt-2" to="/chat">Start one</Link>}>
          {q ? 'Try another word.' : 'Your questions and answers will be saved here.'}
        </EmptyState>
      ) : (
        <>
          <ul className="divide-y divide-line border-y border-line">
            {items.map((c) => (
              <li key={c.id} className="flex items-center gap-3 py-3">
                <Link to={`/chat/${c.id}`} className="min-w-0 flex-1 hover:text-brand"><span className="block truncate font-medium">{c.title}</span>
                  <span className="text-xs text-muted" title={formatDate(c.updated_at, true)}>{timeAgo(c.updated_at)}</span></Link>
                <button className="rounded p-1.5 text-muted hover:text-bad" aria-label={`Delete ${c.title}`} onClick={() => remove(c)}><Trash2 className="h-4 w-4" /></button>
              </li>
            ))}
          </ul>
          <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
    </PageBody>
  )
}
