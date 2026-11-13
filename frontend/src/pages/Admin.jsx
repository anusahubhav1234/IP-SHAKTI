import { useState } from 'react'
import { CheckCircle2, CircleAlert, MinusCircle } from 'lucide-react'
import { PageBody } from '../layouts/AppLayout'
import { ErrorNote, Figure, PageHeader, Pagination, Section, Spinner, StatusBadge, Tabs } from '../components/ui'
import { useAuth } from '../contexts/AuthContext'
import { useAsync } from '../hooks/useAsync'
import { adminApi, documentsApi, errorMessage } from '../services/api'
import { formatBytes, formatDate } from '../utils/format'

function Overview() {
  const { data: o, loading, error, reload } = useAsync(() => adminApi.overview(), [])
  if (loading) return <Spinner label="Loading" />
  if (error) return <ErrorNote onRetry={reload}>{error}</ErrorNote>
  return (
    <div className="space-y-8">
      <div className="flex flex-wrap gap-x-10 gap-y-5">
        <Figure label="Users" value={o.users.total} note={`${o.users.active} active`} />
        <Figure label="Documents" value={o.documents.total} note={`${o.documents.by_status.failed} failed`} />
        <Figure label="Passages" value={o.chunks} />
        <Figure label="Questions" value={o.messages.user} />
        <Figure label="Evaluation runs" value={o.evaluation_runs} />
      </div>
      <Section title="Recent processing failures">
        {o.processing_failures.length === 0 ? <p className="text-sm text-muted">None.</p> : (
          <ul className="divide-y divide-line border-y border-line text-sm">{o.processing_failures.map((f) => <li key={f.document_id} className="py-2"><span className="font-medium">{f.title}</span><span className="ml-2 text-bad">{f.error}</span></li>)}</ul>
        )}
      </Section>
    </div>
  )
}

function Users() {
  const { user: me } = useAuth()
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const [err, setErr] = useState('')
  const { data, loading, error, reload } = useAsync(() => adminApi.users({ q: q || undefined, limit: 25, offset }), [q, offset])
  async function update(u, body) {
    setErr('')
    try { await adminApi.updateUser(u.id, body); reload() } catch (e) { setErr(errorMessage(e)) }
  }
  return (
    <>
      <input className="field mb-4" aria-label="Search users" placeholder="Search by name or email" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0) }} />
      <ErrorNote>{err || error}</ErrorNote>
      {loading && !data ? <Spinner label="Loading users" /> : data && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[42rem] text-sm">
            <thead><tr className="border-b border-line text-left text-xs text-muted"><th className="py-2 font-medium">User</th><th className="font-medium">Role</th><th className="font-medium">Docs</th><th className="font-medium">Chats</th><th className="font-medium">Last login</th><th /></tr></thead>
            <tbody>{data.items.map((u) => {
              const self = u.id === me.id
              return (
                <tr key={u.id} className="border-b border-line/70">
                  <td className="py-2"><span className="block font-medium">{u.full_name}</span><span className="text-xs text-muted">{u.email}</span></td>
                  <td>{u.role}</td><td>{u.document_count}</td><td>{u.conversation_count}</td><td>{u.last_login_at ? formatDate(u.last_login_at, true) : 'Never'}</td>
                  <td className="space-x-2 whitespace-nowrap text-right">
                    <button className="btn btn-quiet !py-1 text-xs" disabled={self} title={self ? 'You cannot change your own account here' : undefined} onClick={() => update(u, { is_active: !u.is_active })}>{u.is_active ? 'Deactivate' : 'Activate'}</button>
                    <button className="btn btn-quiet !py-1 text-xs" disabled={self} onClick={() => update(u, { role: u.role === 'admin' ? 'user' : 'admin' })}>{u.role === 'admin' ? 'Make user' : 'Make admin'}</button>
                  </td>
                </tr>)
            })}</tbody>
          </table>
          <Pagination total={data.total} limit={25} offset={offset} onChange={setOffset} />
        </div>
      )}
    </>
  )
}

function Docs() {
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const [err, setErr] = useState('')
  const { data, loading, error, reload } = useAsync(() => adminApi.documents({ q: q || undefined, limit: 25, offset }), [q, offset])
  async function remove(d) {
    if (!window.confirm(`Delete “${d.title}” owned by ${d.owner_email}?`)) return
    try { await documentsApi.remove(d.id); reload() } catch (e) { setErr(errorMessage(e)) }
  }
  return (
    <>
      <input className="field mb-4" aria-label="Search documents" placeholder="Search by title" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0) }} />
      <ErrorNote>{err || error}</ErrorNote>
      {loading && !data ? <Spinner label="Loading documents" /> : data && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[42rem] text-sm">
            <thead><tr className="border-b border-line text-left text-xs text-muted"><th className="py-2 font-medium">Title</th><th className="font-medium">Owner</th><th className="font-medium">Size</th><th className="font-medium">Passages</th><th className="font-medium">Status</th><th /></tr></thead>
            <tbody>{data.items.map((d) => (
              <tr key={d.id} className="border-b border-line/70"><td className="max-w-[16rem] truncate py-2">{d.title}</td><td>{d.owner_email}</td><td>{formatBytes(d.size_bytes)}</td><td>{d.chunk_count}</td><td><StatusBadge status={d.status} /></td>
                <td className="text-right"><button className="text-xs text-muted hover:text-bad" onClick={() => remove(d)}>Delete</button></td></tr>))}</tbody>
          </table>
          <Pagination total={data.total} limit={25} offset={offset} onChange={setOffset} />
        </div>
      )}
    </>
  )
}

function Health() {
  const { data: h, loading, error, reload } = useAsync(() => adminApi.health(), [])
  if (loading) return <Spinner label="Checking" />
  if (error) return <ErrorNote onRetry={reload}>{error}</ErrorNote>
  const detail = (c) => Object.entries(c).filter(([k]) => k !== 'ok').map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') || 'none' : v}`).join(' · ')
  return (
    <div>
      <p className="mb-4 text-sm">Overall: <strong className={h.status === 'healthy' ? 'text-ok' : 'text-bad'}>{h.status}</strong> ({h.environment})</p>
      <ul className="divide-y divide-line border-y border-line text-sm">
        {Object.entries(h.checks).map(([name, c]) => (
          <li key={name} className="flex items-start gap-3 py-2.5">
            {c.ok === true ? <CheckCircle2 className="mt-0.5 h-4 w-4 text-ok" aria-label="OK" /> : c.ok === false ? <CircleAlert className="mt-0.5 h-4 w-4 text-bad" aria-label="Problem" /> : <MinusCircle className="mt-0.5 h-4 w-4 text-muted" aria-label="Not checked" />}
            <span className="w-28 font-medium capitalize">{name}</span><span className="text-muted">{detail(c)}</span>
          </li>))}
      </ul>
      <p className="mt-4 text-sm text-muted">Passages without an embedding: {h.chunks_without_embedding} · LLM errors in the last 24 h: {h.llm_errors_last_24h}</p>
      <p className="mt-1 text-xs text-muted">The LLM check only shows that a key is configured. Run <code>python -m app.scripts.check_llm</code> to test it for real.</p>
    </div>
  )
}

export default function Admin() {
  const [tab, setTab] = useState('overview')
  const body = { overview: <Overview />, users: <Users />, docs: <Docs />, health: <Health /> }[tab]
  return (
    <PageBody wide>
      <PageHeader title="Administration" />
      <Tabs value={tab} onChange={setTab} tabs={[{ value: 'overview', label: 'Overview' }, { value: 'users', label: 'Users' }, { value: 'docs', label: 'Documents' }, { value: 'health', label: 'System health' }]} />
      {body}
    </PageBody>
  )
}
