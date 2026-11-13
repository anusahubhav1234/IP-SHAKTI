import { useEffect, useState } from 'react'
import { BadgeCheck, TriangleAlert } from 'lucide-react'
import { PageBody } from '../layouts/AppLayout'
import { LanguageSelect } from '../components/LanguageSelect'
import { EmptyState, ErrorNote, Field, Notice, PageHeader, Section, Spinner } from '../components/ui'
import { documentsApi, errorMessage } from '../services/api'

const DEFAULT_ASPECTS = ['Eligibility criteria', 'Important dates and deadlines', 'Fees', 'Rules and regulations', 'Requirements and required documents']

function Cite({ c }) {
  if (!c) return null
  return <span className="mt-1 block text-xs text-muted">{c.document_title}{c.page_number ? `, p. ${c.page_number}` : ''} · “{c.excerpt.slice(0, 120)}{c.excerpt.length > 120 ? '…' : ''}”</span>
}

function Claims({ items, empty }) {
  if (!items.length) return <p className="text-sm text-muted">{empty}</p>
  return (
    <ul className="space-y-3">
      {items.map((c, i) => (
        <li key={i} className="text-sm">
          <span className="flex items-start gap-1.5">
            {c.verified ? <BadgeCheck className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-label="Verified" /> : <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-label="Not verified" />}
            {c.text}
          </span>
          {c.citations.map((x, j) => <Cite key={j} c={x} />)}
        </li>
      ))}
    </ul>
  )
}

export default function Compare() {
  const [docs, setDocs] = useState([])
  const [selected, setSelected] = useState([])
  const [aspects, setAspects] = useState(DEFAULT_ASPECTS)
  const [custom, setCustom] = useState('')
  const [language, setLanguage] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => { documentsApi.list({ status: 'ready', limit: 100 }).then((r) => setDocs(r.items)).catch((e) => setError(errorMessage(e))) }, [])

  const toggleDoc = (id) => setSelected((s) => s.includes(id) ? s.filter((x) => x !== id) : s.length < 5 ? [...s, id] : s)
  const toggleAspect = (a) => setAspects((s) => s.includes(a) ? s.filter((x) => x !== a) : s.length < 6 ? [...s, a] : s)
  function addCustom(e) {
    e.preventDefault()
    const v = custom.trim()
    if (v && !aspects.includes(v) && aspects.length < 6) setAspects((s) => [...s, v])
    setCustom('')
  }

  async function run() {
    setBusy(true); setError(''); setResult(null)
    try { setResult(await documentsApi.compare({ document_ids: selected, aspects, language: language || undefined })) }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  const titleOf = (id) => result?.documents.find((d) => d.document_id === id)?.title
  const allAspects = [...new Set([...DEFAULT_ASPECTS, ...aspects])]

  return (
    <PageBody wide>
      <PageHeader title="Compare documents" subtitle="Pick 2 to 5 documents and the points to compare. Every cell quotes its source; cells that could not be verified are marked." />
      <div className="grid gap-8 lg:grid-cols-2">
        <Section title="1. Documents" hint={`${selected.length} selected`}>
          {docs.length < 2 ? <EmptyState title="You need at least two ready documents">Upload more documents to use comparison.</EmptyState> : (
            <ul className="max-h-72 divide-y divide-line overflow-y-auto border-y border-line">
              {docs.map((d) => (
                <li key={d.id}><label className="flex cursor-pointer items-center gap-2 px-1 py-2 text-sm hover:bg-line/40">
                  <input type="checkbox" checked={selected.includes(d.id)} disabled={!selected.includes(d.id) && selected.length >= 5} onChange={() => toggleDoc(d.id)} />
                  <span className="truncate">{d.title}</span></label></li>
              ))}
            </ul>
          )}
        </Section>
        <Section title="2. Points to compare" hint="Up to 6">
          <div className="mb-3 flex flex-wrap gap-2">
            {allAspects.map((a) => (
              <button key={a} aria-pressed={aspects.includes(a)} onClick={() => toggleAspect(a)}
                className={`rounded-full border px-3 py-1 text-xs ${aspects.includes(a) ? 'border-brand bg-brand/10 text-brand' : 'border-line text-muted hover:text-ink'}`}>{a}</button>
            ))}
          </div>
          <form onSubmit={addCustom} className="flex gap-2">
            <input className="field" aria-label="Custom aspect" placeholder="Add your own, e.g. Refund policy" maxLength={80} value={custom} onChange={(e) => setCustom(e.target.value)} />
            <button className="btn btn-quiet" disabled={!custom.trim()}>Add</button>
          </form>
          <div className="mt-4"><Field label="Answer language" htmlFor="cmp-lang"><LanguageSelect id="cmp-lang" value={language} onChange={setLanguage} allowAuto label="" /></Field></div>
        </Section>
      </div>
      <button className="btn btn-primary mt-6" disabled={busy || selected.length < 2 || aspects.length === 0} onClick={run}>{busy ? 'Comparing…' : 'Compare'}</button>
      {busy && <div className="mt-4"><Spinner label="Reading the documents and checking every quote. This can take a minute." /></div>}
      <div className="mt-4"><ErrorNote>{error}</ErrorNote></div>

      {result && result.status === 'insufficient_evidence' && <div className="mt-6"><Notice tone="warn">The documents did not contain enough evidence to compare these points.</Notice></div>}
      {result && (
        <div className="mt-10 space-y-10" lang={result.language}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] border-collapse text-sm">
              <thead><tr className="border-b border-line text-left"><th className="w-40 py-2 pr-3 font-medium">Point</th>
                {result.documents.map((d) => <th key={d.document_id} className="px-3 py-2 font-medium">{d.title}</th>)}</tr></thead>
              <tbody>
                {result.rows.map((r) => (
                  <tr key={r.aspect} className="border-b border-line/70 align-top">
                    <th scope="row" className="py-3 pr-3 text-left font-medium">{r.aspect}</th>
                    {r.cells.map((c) => (
                      <td key={c.document_id} className="px-3 py-3" aria-label={titleOf(c.document_id)}>
                        {!c.found ? <span className="text-muted">Not found in this document</span> : (
                          <>
                            <span className="flex items-start gap-1.5">
                              {c.verified ? <BadgeCheck className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-label="Verified" /> : <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-label="Not verified" />}
                              {c.value}
                            </span>
                            <Cite c={c.citation} />
                          </>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid gap-8 md:grid-cols-2">
            <Section title="Similarities"><Claims items={result.similarities} empty="None found." /></Section>
            <Section title="Differences"><Claims items={result.differences} empty="None found." /></Section>
          </div>
        </div>
      )}
    </PageBody>
  )
}
