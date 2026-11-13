import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { PageBody } from '../layouts/AppLayout'
import { EmptyState, ErrorNote, Field, Figure, Notice, PageHeader, Section, Spinner, Tabs } from '../components/ui'
import { useAsync } from '../hooks/useAsync'
import { useChartColors } from '../hooks/useChartColors'
import { analyticsApi, documentsApi, errorMessage, evaluationApi } from '../services/api'
import { MODES, formatDate, languageName, modeLabel } from '../utils/format'

const SAMPLE = `[
  { "question": "What is the minimum attendance?", "language": "en",
    "relevant": [{ "document_id": "<document id>", "page": 3 }] }
]`

function Usage() {
  const colors = useChartColors()
  const { data: o, loading, error, reload } = useAsync(() => analyticsApi.overview(), [])
  if (loading) return <Spinner label="Loading usage" />
  if (error) return <ErrorNote onRetry={reload}>{error}</ErrorNote>
  const activity = o.activity.map((d) => ({ ...d, label: d.date.slice(5) }))
  const langs = Object.entries(o.language_usage).map(([k, v]) => ({ language: languageName(k), questions: v }))
  const modes = Object.entries(o.retrieval_modes).map(([k, v]) => ({ mode: modeLabel(k), answers: v }))
  const tip = { background: colors.surface, border: `1px solid ${colors.line}`, borderRadius: 8, fontSize: 12 }
  return (
    <div className="space-y-10">
      <div className="flex flex-wrap gap-x-10 gap-y-5">
        <Figure label="Questions asked" value={o.messages.user} />
        <Figure label="Answers withheld" value={o.messages.insufficient_evidence} note="not enough evidence or not verified" />
        <Figure label="Avg response" value={o.latency_ms.avg != null ? `${(o.latency_ms.avg / 1000).toFixed(1)} s` : '-'} />
        <Figure label="Feedback" value={`${o.feedback.up} / ${o.feedback.down}`} note="helpful / not helpful" />
      </div>
      <Section title="Activity, last 14 days">
        <div className="h-60" role="img" aria-label="Searches and questions per day">
          <ResponsiveContainer><LineChart data={activity}><CartesianGrid stroke={colors.line} vertical={false} /><XAxis dataKey="label" stroke={colors.muted} fontSize={11} /><YAxis allowDecimals={false} stroke={colors.muted} fontSize={11} width={28} />
            <Tooltip contentStyle={tip} /><Legend /><Line dataKey="chat" name="Questions" stroke={colors.brand} strokeWidth={2} dot={false} /><Line dataKey="search" name="Searches" stroke={colors.warn} strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer>
        </div>
      </Section>
      <div className="grid gap-10 md:grid-cols-2">
        <Section title="Question language">{langs.length ? <div className="h-48"><ResponsiveContainer><BarChart data={langs}><CartesianGrid stroke={colors.line} vertical={false} /><XAxis dataKey="language" stroke={colors.muted} fontSize={11} /><YAxis allowDecimals={false} stroke={colors.muted} fontSize={11} width={28} /><Tooltip contentStyle={tip} /><Bar dataKey="questions" fill={colors.brand} radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div> : <p className="text-sm text-muted">No questions yet.</p>}</Section>
        <Section title="Retrieval mode used">{modes.length ? <div className="h-48"><ResponsiveContainer><BarChart data={modes}><CartesianGrid stroke={colors.line} vertical={false} /><XAxis dataKey="mode" stroke={colors.muted} fontSize={11} /><YAxis allowDecimals={false} stroke={colors.muted} fontSize={11} width={28} /><Tooltip contentStyle={tip} /><Bar dataKey="answers" fill={colors.ok} radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div> : <p className="text-sm text-muted">No answers yet.</p>}</Section>
      </div>
    </div>
  )
}

function Evaluation() {
  const colors = useChartColors()
  const benchmarks = useAsync(() => evaluationApi.benchmarks(), [])
  const runs = useAsync(() => evaluationApi.runs(), [])
  const [name, setName] = useState('')
  const [json, setJson] = useState('')
  const [formError, setFormError] = useState('')
  const [bid, setBid] = useState('')
  const [modes, setModes] = useState(['vector', 'hybrid'])
  const [topK, setTopK] = useState(5)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [runError, setRunError] = useState('')

  async function create(e) {
    e.preventDefault(); setFormError('')
    let items
    try { items = JSON.parse(json) } catch { return setFormError('That is not valid JSON.') }
    if (!Array.isArray(items)) return setFormError('The benchmark must be a JSON array of questions.')
    try { const b = await evaluationApi.createBenchmark({ name, items }); setName(''); setJson(''); setBid(b.id); benchmarks.reload() }
    catch (err) { setFormError(errorMessage(err)) }
  }
  async function run() {
    setBusy(true); setRunError(''); setResult(null)
    try { setResult(await evaluationApi.run({ benchmark_id: bid, modes, top_k: Number(topK) })); runs.reload() }
    catch (e) { setRunError(errorMessage(e)) } finally { setBusy(false) }
  }
  async function removeBench(id) {
    if (!window.confirm('Delete this benchmark and its runs?')) return
    await evaluationApi.removeBenchmark(id).catch(() => {}); if (bid === id) setBid(''); benchmarks.reload(); runs.reload()
  }

  const shown = result?.results ?? result
  const m = shown?.modes
  const k = shown?.top_k
  const rows = m ? Object.values(m).map((x) => ({ mode: x.mode, error: x.error, ...(x.overall || {}), latency: x.latency_ms })) : []
  const chart = rows.filter((r) => !r.error).map((r) => ({ mode: modeLabel(r.mode), 'P@k': r[`precision@${k}`], 'R@k': r[`recall@${k}`], MRR: r.mrr, nDCG: r[`ndcg@${k}`] }))
  const f = (v) => (v == null ? '-' : v.toFixed(3))

  return (
    <div className="space-y-10">
      <Notice tone="info">Results here come only from a benchmark you write yourself, with the pages you mark as correct. Nothing is pre-filled, and unanswerable questions (empty “relevant”) are not scored.</Notice>
      <Section title="1. Benchmark">
        {benchmarks.data?.length > 0 && (
          <ul className="mb-4 divide-y divide-line border-y border-line text-sm">
            {benchmarks.data.map((b) => (
              <li key={b.id} className="flex items-center gap-3 py-2">
                <label className="flex flex-1 cursor-pointer items-center gap-2"><input type="radio" name="bench" checked={bid === b.id} onChange={() => setBid(b.id)} />{b.name}<span className="text-xs text-muted">{b.n_scored} scored of {b.n_items}</span></label>
                <button className="text-xs text-muted hover:text-bad" onClick={() => removeBench(b.id)}>Delete</button>
              </li>
            ))}
          </ul>
        )}
        <details>
          <summary className="cursor-pointer text-sm text-brand">Create a benchmark</summary>
          <form onSubmit={create} className="mt-3 space-y-3">
            <Field label="Name" htmlFor="bn"><input id="bn" className="field" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Questions (JSON)" htmlFor="bj" hint="Use document ids from the document page URL. “page” is optional.">
              <textarea id="bj" className="field font-mono text-xs" rows={7} placeholder={SAMPLE} required value={json} onChange={(e) => setJson(e.target.value)} />
            </Field>
            <ErrorNote>{formError}</ErrorNote>
            <button className="btn btn-primary">Save benchmark</button>
          </form>
        </details>
      </Section>
      <Section title="2. Run">
        <div className="flex flex-wrap items-end gap-5">
          <fieldset><legend className="mb-1 text-xs text-muted">Retrieval modes</legend>
            <div className="flex flex-wrap gap-3 text-sm">{MODES.map((x) => <label key={x.value} className="flex items-center gap-1.5"><input type="checkbox" checked={modes.includes(x.value)} onChange={(e) => setModes((s) => e.target.checked ? [...s, x.value] : s.filter((v) => v !== x.value))} />{x.label}</label>)}</div></fieldset>
          <Field label="Top k" htmlFor="tk"><select id="tk" className="field !w-20" value={topK} onChange={(e) => setTopK(e.target.value)}>{[3, 5, 8, 10].map((n) => <option key={n}>{n}</option>)}</select></Field>
          <button className="btn btn-primary" disabled={!bid || !modes.length || busy} onClick={run}>{busy ? 'Running…' : 'Run evaluation'}</button>
        </div>
        <div className="mt-3"><ErrorNote>{runError}</ErrorNote></div>
        {busy && <Spinner label="Running retrieval for every question" />}
      </Section>
      {m && (
        <Section title="Results" hint={`${shown.n_scored} scored questions, top ${k}`}>
          <div className="overflow-x-auto"><table className="w-full min-w-[34rem] text-sm"><thead><tr className="border-b border-line text-left text-xs text-muted"><th className="py-2 font-medium">Mode</th><th className="font-medium">P@{k}</th><th className="font-medium">R@{k}</th><th className="font-medium">MRR</th><th className="font-medium">nDCG@{k}</th><th className="font-medium">Latency mean / p95</th></tr></thead>
            <tbody>{rows.map((r) => r.error ? <tr key={r.mode} className="border-b border-line/70"><td className="py-2">{modeLabel(r.mode)}</td><td colSpan={5} className="text-warn">{r.error}</td></tr> :
              <tr key={r.mode} className="border-b border-line/70 tabular-nums"><td className="py-2 font-sans">{modeLabel(r.mode)}</td><td>{f(r[`precision@${k}`])}</td><td>{f(r[`recall@${k}`])}</td><td>{f(r.mrr)}</td><td>{f(r[`ndcg@${k}`])}</td><td>{r.latency ? `${r.latency.mean} / ${r.latency.p95} ms` : '-'}</td></tr>)}</tbody></table></div>
          {chart.length > 0 && <div className="mt-6 h-64" role="img" aria-label="Retrieval metrics by mode"><ResponsiveContainer><BarChart data={chart}><CartesianGrid stroke={colors.line} vertical={false} /><XAxis dataKey="mode" stroke={colors.muted} fontSize={11} /><YAxis domain={[0, 1]} stroke={colors.muted} fontSize={11} width={32} /><Tooltip contentStyle={{ background: colors.surface, border: `1px solid ${colors.line}`, fontSize: 12 }} /><Legend />
            <Bar dataKey="P@k" fill={colors.brand} /><Bar dataKey="R@k" fill={colors.ok} /><Bar dataKey="MRR" fill={colors.warn} /><Bar dataKey="nDCG" fill={colors.mark} /></BarChart></ResponsiveContainer></div>}
        </Section>
      )}
      <Section title="Previous runs">
        {!runs.data?.length ? <p className="text-sm text-muted">No runs yet.</p> : (
          <ul className="divide-y divide-line border-y border-line text-sm">
            {runs.data.map((r) => <li key={r.id} className="flex items-center justify-between gap-3 py-2"><span>{r.benchmark_name || 'Benchmark'} · top {r.top_k}</span>
              <span className="text-xs text-muted">{formatDate(r.created_at, true)}</span><button className="text-xs text-brand underline" onClick={() => setResult(r)}>View</button></li>)}
          </ul>
        )}
      </Section>
    </div>
  )
}

export default function Analytics() {
  const [tab, setTab] = useState('usage')
  return (
    <PageBody wide>
      <PageHeader title="Analytics" subtitle="Your own usage and retrieval quality." />
      <Tabs value={tab} onChange={setTab} tabs={[{ value: 'usage', label: 'Usage' }, { value: 'eval', label: 'Retrieval evaluation' }]} />
      {tab === 'usage' ? <Usage /> : <Evaluation />}
    </PageBody>
  )
}
