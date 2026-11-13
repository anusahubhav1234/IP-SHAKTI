import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Check, ChevronDown, Copy, FileText, Menu, MessageSquarePlus, Paperclip, SendHorizontal, ThumbsDown, ThumbsUp, Trash2, TriangleAlert } from 'lucide-react'
import { AnswerText, CitationList } from '../components/Citations'
import { LanguageSelect } from '../components/LanguageSelect'
import { ErrorNote, Spinner } from '../components/ui'
import { useAuth } from '../contexts/AuthContext'
import { usePrefs } from '../contexts/PrefsContext'
import { chatApi, documentsApi, errorMessage, streamChat } from '../services/api'
import { STAGE_LABELS, modeLabel, timeAgo } from '../utils/format'

const SUGGESTIONS = [
  'What is the minimum attendance required for examinations?',
  'Which document mentions the fee payment deadline?',
  'What documents are required for a scholarship application?',
  'Summarize the most recently uploaded document.',
]
const STAGE_ORDER = ['rewriting', 'retrieving', 'generating', 'verifying']

function fromServer(m) {
  return {
    id: m.id, role: m.role, content: m.content, citations: m.citations || [], language: m.response_language,
    status: m.role === 'assistant' ? (m.insufficient_evidence ? 'no_answer' : 'answered') : undefined,
    feedback: m.my_feedback ?? null, latency: m.latency_ms,
  }
}

function plainText(m) {
  const src = (m.citations || []).map((c) => `[${c.number}] ${c.document_title}${c.page_number ? `, page ${c.page_number}` : ''}`)
  return src.length ? `${m.content}\n\nSources:\n${src.join('\n')}` : m.content
}

function AssistantMessage({ m, onFeedback }) {
  const [copied, setCopied] = useState(false)
  const [active, setActive] = useState(null)
  const answered = m.status === 'answered'
  async function copy() {
    try { await navigator.clipboard.writeText(plainText(m)); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* clipboard blocked */ }
  }
  return (
    <div className="max-w-[46rem]">
      {answered ? (
        <>
          <AnswerText text={m.content} lang={m.language} onCite={setActive} />
          <CitationList citations={m.citations} activeNumber={active} />
        </>
      ) : (
        <div className="flex items-start gap-2 rounded-panel border border-warn/40 bg-warn/10 px-4 py-3 text-sm" lang={m.language}>
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden="true" />
          <div>
            <p>{m.content}</p>
            <p className="mt-1 text-xs text-muted">
              {m.status === 'unverified_withheld'
                ? 'An answer was drafted, but none of its quotes could be found in your documents, so it is not shown.'
                : 'Try different words, or upload the document that covers this topic.'}
            </p>
          </div>
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-1 text-xs text-muted">
        <button className="btn btn-quiet !px-2 !py-1" onClick={copy} aria-label="Copy answer">{copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}{copied ? 'Copied' : 'Copy'}</button>
        {m.id && (
          <>
            <button className={`btn btn-quiet !px-2 !py-1 ${m.feedback === 1 ? '!border-ok !text-ok' : ''}`} aria-pressed={m.feedback === 1} aria-label="Good answer" onClick={() => onFeedback(m, 1)}><ThumbsUp className="h-3.5 w-3.5" /></button>
            <button className={`btn btn-quiet !px-2 !py-1 ${m.feedback === -1 ? '!border-bad !text-bad' : ''}`} aria-pressed={m.feedback === -1} aria-label="Poor answer" onClick={() => onFeedback(m, -1)}><ThumbsDown className="h-3.5 w-3.5" /></button>
          </>
        )}
        <span className="ml-2">
          {m.mode && modeLabel(m.mode)}{m.latency != null && ` · ${(m.latency / 1000).toFixed(1)} s`}
          {m.rewritten && <> · searched for “{m.rewritten}”</>}
        </span>
      </div>
    </div>
  )
}

export default function Chat() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { prefs } = usePrefs()
  const [conversations, setConversations] = useState([])
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [language, setLanguage] = useState(user?.preferred_language && user.preferred_language !== 'en' ? user.preferred_language : null)
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState(null)
  const [error, setError] = useState('')
  const [loadingConv, setLoadingConv] = useState(false)
  const [docs, setDocs] = useState([])
  const [scope, setScope] = useState([])
  const [scopeOpen, setScopeOpen] = useState(false)
  const [sideOpen, setSideOpen] = useState(false)
  const [attachments, setAttachments] = useState([])
  const bottom = useRef(null)
  const lastQuestion = useRef('')
  const skipLoad = useRef(null)
  const fileInput = useRef(null)

  const refreshList = useCallback(() => chatApi.conversations({ limit: 50 }).then((r) => setConversations(r.items)).catch(() => {}), [])
  const refreshDocs = useCallback(() => documentsApi.list({ status: 'ready', limit: 100 }).then((r) => setDocs(r.items)).catch(() => {}), [])
  useEffect(() => { refreshList(); refreshDocs() }, [refreshList, refreshDocs])

  useEffect(() => {
    if (!conversationId) { setMessages([]); setError(''); return }
    if (skipLoad.current === conversationId) { skipLoad.current = null; return }
    let live = true
    setLoadingConv(true); setError('')
    chatApi.conversation(conversationId)
      .then((c) => live && setMessages(c.messages.map(fromServer)))
      .catch((e) => live && setError(errorMessage(e, 'Could not open this conversation.')))
      .finally(() => live && setLoadingConv(false))
    return () => { live = false }
  }, [conversationId])

  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    bottom.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'end' })
  }, [messages, busy, stage])

  async function send(text) {
    const q = (text ?? input).trim()
    if (!q || busy) return
    lastQuestion.current = q
    setInput(''); setError(''); setBusy(true); setStage('started')
    setMessages((ms) => [...ms, { role: 'user', content: q }])
    try {
      const res = await streamChat({
        message: q, conversation_id: conversationId || undefined, language: language || undefined,
        mode: prefs.mode, top_k: prefs.topK, document_ids: scope.length ? scope : undefined,
      }, { onStage: setStage })
      setMessages((ms) => [...ms, {
        id: res.message_id, role: 'assistant', content: res.answer, citations: res.citations, language: res.language,
        status: res.status, feedback: null, latency: res.latency_ms, mode: res.retrieval_mode, rewritten: res.rewritten_query,
      }])
      if (!conversationId) { skipLoad.current = res.conversation_id; navigate(`/chat/${res.conversation_id}`, { replace: true }) }
      refreshList()
    } catch (e) {
      setError(errorMessage(e))
    } finally { setBusy(false); setStage(null) }
  }

  async function feedback(m, rating) {
    const next = m.feedback === rating ? null : rating
    setMessages((ms) => ms.map((x) => (x.id === m.id ? { ...x, feedback: next } : x)))
    try { next === null ? await chatApi.clearFeedback(m.id) : await chatApi.feedback(m.id, next) }
    catch { setMessages((ms) => ms.map((x) => (x.id === m.id ? { ...x, feedback: m.feedback } : x))) }
  }

  async function removeConversation(id) {
    if (!window.confirm('Delete this conversation? This cannot be undone.')) return
    await chatApi.removeConversation(id).catch(() => {})
    if (id === conversationId) navigate('/chat')
    refreshList()
  }

  async function attach(files) {
    for (const file of files) {
      const entry = { key: `${file.name}-${Date.now()}`, name: file.name, status: 'uploading' }
      setAttachments((a) => [...a, entry])
      const patch = (p) => setAttachments((a) => a.map((x) => (x.key === entry.key ? { ...x, ...p } : x)))
      try {
        const doc = await documentsApi.upload(file)
        patch({ status: 'processing', id: doc.id })
        for (let i = 0; i < 90; i++) {
          await new Promise((r) => setTimeout(r, 2000))
          const s = await documentsApi.status(doc.id)
          if (s.status === 'ready') { patch({ status: 'ready' }); refreshDocs(); break }
          if (s.status === 'failed') { patch({ status: 'failed', error: s.error }); break }
        }
      } catch (e) { patch({ status: 'failed', error: errorMessage(e) }) }
    }
  }

  const empty = !conversationId && messages.length === 0
  const scopeLabel = scope.length ? `${scope.length} document${scope.length > 1 ? 's' : ''}` : 'All documents'

  return (
    <div className="flex h-full">
      <aside className={`${sideOpen ? 'absolute inset-y-0 left-0 z-30 flex' : 'hidden'} w-64 shrink-0 flex-col border-r border-line bg-surface md:static md:flex`} aria-label="Conversations">
        <div className="p-3">
          <Link to="/chat" onClick={() => setSideOpen(false)} className="btn btn-primary w-full"><MessageSquarePlus className="h-4 w-4" aria-hidden="true" />New conversation</Link>
        </div>
        <ul className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {conversations.length === 0 && <li className="px-2 py-3 text-xs text-muted">Your conversations will be listed here.</li>}
          {conversations.map((c) => (
            <li key={c.id} className="group relative">
              <Link to={`/chat/${c.id}`} onClick={() => setSideOpen(false)}
                className={`block rounded-field px-3 py-2 pr-9 text-sm ${c.id === conversationId ? 'bg-brand/10 font-medium text-brand' : 'hover:bg-line/50'}`}>
                <span className="block truncate">{c.title}</span>
                <span className="text-xs text-muted">{timeAgo(c.updated_at)}</span>
              </Link>
              <button aria-label={`Delete conversation ${c.title}`} onClick={() => removeConversation(c.id)}
                className="absolute right-1 top-2 rounded p-1.5 text-muted opacity-0 hover:text-bad focus:opacity-100 group-hover:opacity-100"><Trash2 className="h-3.5 w-3.5" /></button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-line px-4 py-2 md:hidden">
          <button className="btn btn-quiet !px-2" onClick={() => setSideOpen((v) => !v)} aria-label="Show conversations"><Menu className="h-4 w-4" /></button>
          <span className="text-sm text-muted">Conversations</span>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl space-y-7 px-5 py-8">
            {loadingConv && <Spinner label="Opening conversation" />}
            {empty && !loadingConv && (
              <div className="pt-6">
                <h1 className="font-display text-3xl font-bold">What do you want to know?</h1>
                <p className="mt-2 max-w-lg text-sm text-muted">Answers come only from your documents, with the page and the quote. Try one of these, or ask your own question in English, Hindi or Telugu.</p>
                <ul className="mt-6 divide-y divide-line border-y border-line">
                  {SUGGESTIONS.map((s) => (
                    <li key={s}><button className="w-full px-1 py-3 text-left text-sm hover:text-brand" onClick={() => send(s)}>{s}</button></li>
                  ))}
                </ul>
                {docs.length === 0 && (
                  <p className="mt-6 text-sm text-warn">You have no ready documents yet. <Link to="/upload" className="underline">Upload one</Link> first, or attach a file below.</p>
                )}
              </div>
            )}

            {messages.map((m, i) => m.role === 'user' ? (
              <div key={i} className="flex justify-end"><p className="max-w-[85%] whitespace-pre-wrap rounded-panel bg-brand/10 px-4 py-2.5 text-[15px]">{m.content}</p></div>
            ) : (
              <AssistantMessage key={m.id || i} m={m} onFeedback={feedback} />
            ))}

            {busy && (
              <div className="max-w-[46rem]" role="status" aria-live="polite">
                <ol className="space-y-1 text-sm">
                  {STAGE_ORDER.filter((s) => s !== 'rewriting' || stage === 'rewriting' || messages.length > 1).map((s) => {
                    const idx = STAGE_ORDER.indexOf(s), cur = STAGE_ORDER.indexOf(stage)
                    const done = cur > idx
                    return (
                      <li key={s} className={done ? 'text-muted' : s === stage ? 'font-medium' : 'text-muted/50'}>
                        {done ? <Check className="mr-1.5 inline h-3.5 w-3.5 text-ok" aria-hidden="true" /> : s === stage ? <Spinner /> : <span className="mr-1.5 inline-block w-3.5" />}
                        {s !== stage && STAGE_LABELS[s]}{s === stage && <span className="ml-1">{STAGE_LABELS[s]}</span>}
                      </li>
                    )
                  })}
                </ol>
              </div>
            )}
            <ErrorNote onRetry={lastQuestion.current ? () => { setMessages((ms) => ms.slice(0, -1)); send(lastQuestion.current) } : undefined}>{error}</ErrorNote>
            <div ref={bottom} />
          </div>
        </div>

        <div className="border-t border-line bg-paper px-4 pb-4 pt-3">
          <div className="mx-auto w-full max-w-3xl">
            {attachments.length > 0 && (
              <ul className="mb-2 flex flex-wrap gap-2 text-xs">
                {attachments.map((a) => (
                  <li key={a.key} className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1">
                    <FileText className="h-3 w-3" aria-hidden="true" />{a.name}
                    <span className={a.status === 'failed' ? 'text-bad' : a.status === 'ready' ? 'text-ok' : 'text-muted'}>
                      {a.status === 'uploading' ? 'uploading…' : a.status === 'processing' ? 'processing…' : a.status === 'ready' ? 'added to your library' : (a.error || 'failed')}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <form onSubmit={(e) => { e.preventDefault(); send() }} className="rounded-panel border border-line bg-surface p-2 focus-within:border-brand">
              <label htmlFor="question" className="sr-only">Your question</label>
              <textarea id="question" rows={2} maxLength={1000} value={input} onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
                placeholder="Ask about your documents…" className="w-full resize-none bg-transparent px-2 py-1 text-[15px] outline-none placeholder:text-muted/70" />
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <input ref={fileInput} type="file" hidden multiple accept=".pdf,.docx,.txt,.csv" onChange={(e) => { attach([...e.target.files]); e.target.value = '' }} />
                <button type="button" className="btn btn-quiet !px-2 !py-1.5" onClick={() => fileInput.current?.click()} aria-label="Attach a document to your library"><Paperclip className="h-4 w-4" /></button>
                <LanguageSelect id="answer-language" value={language} onChange={setLanguage} allowAuto />
                <div className="relative">
                  <button type="button" className="btn btn-quiet !py-1.5" aria-expanded={scopeOpen} onClick={() => setScopeOpen((v) => !v)}>
                    {scopeLabel}<ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  {scopeOpen && (
                    <div className="absolute bottom-full left-0 z-20 mb-2 max-h-64 w-72 overflow-y-auto rounded-panel border border-line bg-surface p-2 shadow-lg">
                      <button type="button" className="mb-1 w-full rounded px-2 py-1 text-left text-xs text-brand underline" onClick={() => setScope([])}>Search all documents</button>
                      {docs.length === 0 && <p className="px-2 py-1 text-xs text-muted">No ready documents.</p>}
                      {docs.map((d) => (
                        <label key={d.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-line/50">
                          <input type="checkbox" checked={scope.includes(d.id)} onChange={(e) => setScope((s) => e.target.checked ? [...s, d.id] : s.filter((x) => x !== d.id))} />
                          <span className="truncate">{d.title}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
                <button className="btn btn-primary ml-auto !py-1.5" disabled={busy || !input.trim()} aria-label="Send question"><SendHorizontal className="h-4 w-4" />Send</button>
              </div>
            </form>
            <p className="mt-2 text-center text-xs text-muted">Press Enter to send, Shift+Enter for a new line. Check the quoted sources before relying on an answer.</p>
          </div>
        </div>
      </section>
    </div>
  )
}
