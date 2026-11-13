import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FileUp, FolderOpen, Search, Tag, Trash2, X } from 'lucide-react'
import { PageBody } from '../layouts/AppLayout'
import { EmptyState, ErrorNote, PageHeader, Pagination, Spinner, StatusBadge } from '../components/ui'
import { categoriesApi, documentsApi, errorMessage } from '../services/api'
import { formatBytes, formatDate, languageName } from '../utils/format'

const LIMIT = 15
const TYPE_LABEL = { pdf: 'PDF', docx: 'Word', txt: 'Text', csv: 'CSV', faq: 'FAQ' }

export default function Library() {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState(null)
  const [categories, setCategories] = useState([])
  const [newCategory, setNewCategory] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      setData(await documentsApi.list({ q: q || undefined, status: status || undefined, category_id: categoryId || undefined, limit: LIMIT, offset }))
      setError('')
    } catch (e) { setError(errorMessage(e)) } finally { setLoading(false) }
  }, [q, status, categoryId, offset])

  useEffect(() => { const t = setTimeout(load, q ? 250 : 0); return () => clearTimeout(t) }, [load, q])
  useEffect(() => { categoriesApi.list().then(setCategories).catch(() => {}) }, [])
  // keep polling while anything is still being processed
  useEffect(() => {
    if (!data?.items.some((d) => d.status === 'pending' || d.status === 'processing')) return
    const t = setInterval(() => load(true), 3000)
    return () => clearInterval(t)
  }, [data, load])

  async function remove(d) {
    if (!window.confirm(`Delete “${d.title}” and all its indexed passages? This cannot be undone.`)) return
    try { await documentsApi.remove(d.id); load(true) } catch (e) { setError(errorMessage(e)) }
  }
  async function addCategory(e) {
    e.preventDefault()
    if (!newCategory.trim()) return
    try { const c = await categoriesApi.create(newCategory.trim()); setCategories((cs) => [...cs, c].sort((a, b) => a.name.localeCompare(b.name))); setNewCategory('') }
    catch (err) { setError(errorMessage(err)) }
  }
  async function removeCategory(c) {
    if (!window.confirm(`Delete the category “${c.name}”? Documents in it are kept.`)) return
    await categoriesApi.remove(c.id).catch(() => {})
    setCategories((cs) => cs.filter((x) => x.id !== c.id))
    if (categoryId === c.id) setCategoryId('')
    load(true)
  }

  return (
    <PageBody wide>
      <PageHeader title="Library" subtitle="Everything you have uploaded. Only you can search these documents."
        actions={<Link className="btn btn-primary" to="/upload"><FileUp className="h-4 w-4" aria-hidden="true" />Upload documents</Link>} />

      <div className="mb-4 flex flex-wrap gap-3">
        <div className="relative min-w-[14rem] flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted" aria-hidden="true" />
          <input className="field !pl-9" placeholder="Search by title or file name" aria-label="Search documents" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0) }} />
        </div>
        <select className="field !w-auto" aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0) }}>
          <option value="">Any status</option><option value="ready">Ready</option><option value="processing">Processing</option><option value="pending">Queued</option><option value="failed">Failed</option>
        </select>
        <select className="field !w-auto" aria-label="Filter by category" value={categoryId} onChange={(e) => { setCategoryId(e.target.value); setOffset(0) }}>
          <option value="">All categories</option>{categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-2 text-sm">
        <Tag className="h-4 w-4 text-muted" aria-hidden="true" />
        {categories.map((c) => (
          <span key={c.id} className="inline-flex items-center gap-1 rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs">
            {c.name}<button aria-label={`Delete category ${c.name}`} className="text-muted hover:text-bad" onClick={() => removeCategory(c)}><X className="h-3 w-3" /></button>
          </span>
        ))}
        <form onSubmit={addCategory} className="flex gap-1">
          <input className="field !w-40 !py-1 text-xs" aria-label="New category name" placeholder="New category" maxLength={80} value={newCategory} onChange={(e) => setNewCategory(e.target.value)} />
          <button className="btn btn-quiet !px-2 !py-1 text-xs" disabled={!newCategory.trim()}>Add</button>
        </form>
      </div>

      <ErrorNote onRetry={() => load()}>{error}</ErrorNote>
      {loading && !data ? <Spinner label="Loading documents" /> : data?.items.length === 0 ? (
        <EmptyState icon={FolderOpen} title={q || status || categoryId ? 'No documents match' : 'Your library is empty'}
          action={!q && !status && !categoryId ? <Link className="btn btn-primary mt-2" to="/upload">Upload a document</Link> : null}>
          {q || status || categoryId ? 'Try removing a filter or changing the search words.' : 'Upload a PDF, Word, text or CSV file to start asking questions.'}
        </EmptyState>
      ) : data && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <thead><tr className="border-b border-line text-left text-xs text-muted">
              <th className="py-2 pr-3 font-medium">Title</th><th className="px-3 font-medium">Type</th><th className="px-3 font-medium">Language</th>
              <th className="px-3 font-medium">Size</th><th className="px-3 font-medium">Passages</th><th className="px-3 font-medium">Added</th><th className="px-3 font-medium">Status</th><th /></tr></thead>
            <tbody>
              {data.items.map((d) => (
                <tr key={d.id} className="border-b border-line/70">
                  <td className="max-w-[20rem] py-3 pr-3"><Link to={`/documents/${d.id}`} className="block truncate font-medium hover:text-brand">{d.title}</Link>
                    <span className="block truncate text-xs text-muted">{d.filename}</span></td>
                  <td className="px-3">{TYPE_LABEL[d.source_type] || d.source_type}</td>
                  <td className="px-3">{d.language ? languageName(d.language) : '-'}</td>
                  <td className="px-3 tabular-nums">{formatBytes(d.size_bytes)}</td>
                  <td className="px-3 tabular-nums">{d.chunk_count}{d.page_count ? ` · ${d.page_count} p` : ''}</td>
                  <td className="px-3 whitespace-nowrap">{formatDate(d.uploaded_at)}</td>
                  <td className="px-3"><StatusBadge status={d.status} /></td>
                  <td className="pl-3 text-right"><button className="rounded p-1.5 text-muted hover:text-bad" aria-label={`Delete ${d.title}`} onClick={() => remove(d)}><Trash2 className="h-4 w-4" /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </div>
      )}
    </PageBody>
  )
}
