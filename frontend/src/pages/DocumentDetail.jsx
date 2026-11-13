import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, MessageSquare, RefreshCw, Trash2 } from 'lucide-react'
import { PageBody } from '../layouts/AppLayout'
import { ErrorNote, PageHeader, Pagination, Section, Spinner, StatusBadge } from '../components/ui'
import { documentsApi, errorMessage } from '../services/api'
import { formatBytes, formatDate, languageName } from '../utils/format'

const LIMIT = 20

export default function DocumentDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [doc, setDoc] = useState(null)
  const [error, setError] = useState('')
  const [chunks, setChunks] = useState(null)
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState('')
  const [pdfUrl, setPdfUrl] = useState(null)
  const [pdfPage, setPdfPage] = useState(1)

  const load = useCallback(() => documentsApi.get(id).then((d) => { setDoc(d); setError('') }).catch((e) => setError(errorMessage(e))), [id])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!doc || (doc.status !== 'pending' && doc.status !== 'processing')) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [doc, load])
  useEffect(() => {
    if (doc?.status !== 'ready') return
    documentsApi.chunks(id, { limit: LIMIT, offset, page: page || undefined }).then(setChunks).catch((e) => setError(errorMessage(e)))
  }, [id, doc?.status, offset, page])
  useEffect(() => {
    if (doc?.source_type !== 'pdf') return
    let url
    documentsApi.fileUrl(id).then((u) => { url = u; setPdfUrl(u) }).catch(() => {})
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [id, doc?.source_type])

  async function remove() {
    if (!window.confirm(`Delete “${doc.title}”? This cannot be undone.`)) return
    try { await documentsApi.remove(id); navigate('/documents') } catch (e) { setError(errorMessage(e)) }
  }
  async function reprocess() {
    try { setDoc(await documentsApi.reprocess(id)) } catch (e) { setError(errorMessage(e)) }
  }

  if (!doc) return <PageBody>{error ? <ErrorNote>{error}</ErrorNote> : <Spinner label="Loading document" />}</PageBody>
  const meta = [['Type', doc.source_type.toUpperCase()], ['Language', doc.language ? languageName(doc.language) : '-'], ['Size', formatBytes(doc.size_bytes)],
    ['Pages', doc.page_count ?? '-'], ['Passages', doc.chunk_count], ['Uploaded', formatDate(doc.uploaded_at, true)]]

  return (
    <PageBody wide>
      <Link to="/documents" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink"><ArrowLeft className="h-4 w-4" aria-hidden="true" />Library</Link>
      <PageHeader title={doc.title} subtitle={doc.filename}
        actions={<>
          <Link to="/chat" className="btn btn-primary"><MessageSquare className="h-4 w-4" aria-hidden="true" />Ask questions</Link>
          <button className="btn btn-quiet" onClick={reprocess}><RefreshCw className="h-4 w-4" aria-hidden="true" />Reprocess</button>
          <button className="btn btn-quiet text-bad" onClick={remove}><Trash2 className="h-4 w-4" aria-hidden="true" />Delete</button>
        </>} />
      <ErrorNote>{error}</ErrorNote>
      <dl className="mb-8 flex flex-wrap items-end gap-x-8 gap-y-3 text-sm">
        <div><dt className="text-xs text-muted">Status</dt><dd><StatusBadge status={doc.status} /></dd></div>
        {meta.map(([k, v]) => <div key={k}><dt className="text-xs text-muted">{k}</dt><dd className="font-medium">{v}</dd></div>)}
      </dl>
      {doc.status === 'failed' && <p className="mb-6 text-sm text-bad">Processing failed. Try Reprocess, or upload the file again.</p>}
      {(doc.status === 'pending' || doc.status === 'processing') && <Spinner label="Processing this document" />}

      {pdfUrl && (
        <Section title="Original file" hint="Opens at the page you choose.">
          <div className="mb-2 flex items-center gap-2 text-sm">
            <label htmlFor="pdfpage">Go to page</label>
            <input id="pdfpage" type="number" min={1} max={doc.page_count || undefined} className="field !w-24 !py-1" value={pdfPage} onChange={(e) => setPdfPage(Math.max(1, Number(e.target.value) || 1))} />
          </div>
          <iframe key={pdfPage} title={`${doc.title}, page ${pdfPage}`} src={`${pdfUrl}#page=${pdfPage}`} className="h-[32rem] w-full rounded-panel border border-line" />
        </Section>
      )}

      {doc.status === 'ready' && (
        <Section title="Indexed passages" hint="This is exactly the text the assistant can search and quote.">
          <div className="mb-3 flex items-center gap-2 text-sm">
            <label htmlFor="pf">Page</label>
            <input id="pf" type="number" min={1} placeholder="All" className="field !w-24 !py-1" value={page} onChange={(e) => { setPage(e.target.value); setOffset(0) }} />
          </div>
          {!chunks ? <Spinner label="Loading passages" /> : chunks.items.length === 0 ? <p className="text-sm text-muted">No passages found.</p> : (
            <ol className="divide-y divide-line border-y border-line">
              {chunks.items.map((c) => (
                <li key={c.id} className="py-3">
                  <div className="mb-1 flex flex-wrap gap-x-3 text-xs text-muted">
                    <span>#{c.chunk_index + 1}</span>{c.page_number && <button className="underline" onClick={() => setPdfPage(c.page_number)}>Page {c.page_number}</button>}
                    {c.section_heading && <span>{c.section_heading}</span>}
                  </div>
                  <p className="whitespace-pre-wrap text-sm" lang={c.language || undefined}>{c.text}</p>
                </li>
              ))}
            </ol>
          )}
          {chunks && <Pagination total={chunks.total} limit={LIMIT} offset={offset} onChange={setOffset} />}
        </Section>
      )}
    </PageBody>
  )
}
