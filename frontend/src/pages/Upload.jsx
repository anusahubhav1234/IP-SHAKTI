import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, FileText, Upload as UploadIcon, XCircle } from 'lucide-react'
import { PageBody } from '../layouts/AppLayout'
import { Field, PageHeader, Spinner } from '../components/ui'
import { categoriesApi, documentsApi, errorMessage } from '../services/api'
import { formatBytes } from '../utils/format'

const ACCEPT = '.pdf,.docx,.txt,.csv'
const STAGES = { extracting: 'Reading the file', cleaning: 'Cleaning the text', chunking: 'Splitting into passages', embedding: 'Building the search index', storing: 'Saving', done: 'Done' }

export default function Upload() {
  const [items, setItems] = useState([])
  const [categories, setCategories] = useState([])
  const [categoryId, setCategoryId] = useState('')
  const [asFaq, setAsFaq] = useState(false)
  const [drag, setDrag] = useState(false)
  const input = useRef(null)
  useEffect(() => { categoriesApi.list().then(setCategories).catch(() => {}) }, [])

  const patch = useCallback((key, p) => setItems((xs) => xs.map((x) => (x.key === key ? { ...x, ...p } : x))), [])

  async function process(entry, file) {
    try {
      const doc = await documentsApi.upload(file, { categoryId: categoryId || undefined, asFaq: asFaq && /\.csv$/i.test(file.name) }, (progress) => patch(entry.key, { progress }))
      patch(entry.key, { state: 'processing', id: doc.id, title: doc.title })
      for (let i = 0; i < 150; i++) {
        await new Promise((r) => setTimeout(r, 1500))
        const s = await documentsApi.status(doc.id)
        patch(entry.key, { stage: s.stage })
        if (s.status === 'ready') return patch(entry.key, { state: 'ready', chunks: s.chunk_count, note: s.error })
        if (s.status === 'failed') return patch(entry.key, { state: 'failed', error: s.error })
      }
      patch(entry.key, { state: 'failed', error: 'Processing is taking longer than expected. Check the library later.' })
    } catch (e) { patch(entry.key, { state: 'failed', error: errorMessage(e) }) }
  }

  function add(files) {
    for (const file of files) {
      const entry = { key: `${file.name}-${file.size}-${Math.random()}`, name: file.name, size: file.size, state: 'uploading', progress: 0 }
      setItems((xs) => [entry, ...xs])
      process(entry, file)
    }
  }

  return (
    <PageBody>
      <PageHeader title="Upload documents" subtitle="PDF, Word (.docx), text and CSV files up to 20 MB. Scanned PDF pages are read with OCR." />
      <div className="mb-6 grid gap-4 sm:grid-cols-2">
        <Field label="Category (optional)" htmlFor="cat">
          <select id="cat" className="field" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">No category</option>{categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <label className="flex items-start gap-2 self-end pb-2 text-sm">
          <input type="checkbox" className="mt-1" checked={asFaq} onChange={(e) => setAsFaq(e.target.checked)} />
          <span>Treat CSV files as an FAQ<span className="block text-xs text-muted">Needs “question” and “answer” columns. Each row becomes one searchable passage.</span></span>
        </label>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); add([...e.dataTransfer.files]) }}
        className={`flex flex-col items-center gap-3 rounded-panel border-2 border-dashed px-6 py-14 text-center transition-colors ${drag ? 'border-brand bg-brand/5' : 'border-line'}`}>
        <UploadIcon className="h-8 w-8 text-muted" aria-hidden="true" />
        <p className="font-medium">Drop files here</p>
        <button className="btn btn-primary" onClick={() => input.current?.click()}>Choose files</button>
        <input ref={input} type="file" hidden multiple accept={ACCEPT} onChange={(e) => { add([...e.target.files]); e.target.value = '' }} />
      </div>

      {items.length > 0 && (
        <ul className="mt-8 divide-y divide-line border-y border-line">
          {items.map((x) => (
            <li key={x.key} className="flex items-start gap-3 py-3">
              <FileText className="mt-0.5 h-5 w-5 shrink-0 text-muted" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="truncate font-medium">{x.name}</span><span className="text-xs text-muted">{formatBytes(x.size)}</span>
                </div>
                {x.state === 'uploading' && <div className="mt-1.5"><div className="h-1.5 overflow-hidden rounded bg-line" role="progressbar" aria-valuenow={x.progress} aria-valuemin={0} aria-valuemax={100} aria-label={`Uploading ${x.name}`}><div className="h-full bg-brand transition-all" style={{ width: `${x.progress}%` }} /></div></div>}
                {x.state === 'processing' && <p className="mt-1 text-sm text-muted"><Spinner label={STAGES[x.stage] || 'Queued'} /></p>}
                {x.state === 'ready' && (
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ok"><CheckCircle2 className="h-4 w-4" aria-hidden="true" />Ready, {x.chunks} passages indexed.
                    <Link className="text-brand underline" to={`/documents/${x.id}`}>Open</Link><Link className="text-brand underline" to="/chat">Ask about it</Link></p>
                )}
                {x.state === 'ready' && x.note && <p className="mt-1 text-xs text-warn">{x.note}</p>}
                {x.state === 'failed' && <p className="mt-1 flex items-start gap-1.5 text-sm text-bad"><XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />{x.error}</p>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </PageBody>
  )
}
