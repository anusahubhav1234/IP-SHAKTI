import { useState } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { BadgeCheck, FileX2, ShieldAlert } from 'lucide-react'

/** Answer text. [1] markers become small highlighter tabs that open the matching source below. */
export function AnswerText({ text, lang, onCite }) {
  const md = text.replace(/\[(\d+)\]/g, (_, n) => `[${n}](#cite-${n})`)
  return (
    <div className="prose-answer text-[15px]" lang={lang}>
      <ReactMarkdown
        components={{
          a: ({ href, children }) => {
            const m = /^#cite-(\d+)$/.exec(href || '')
            if (!m) return <span>{children}</span> // never render links coming from model output
            return (
              <button
                type="button"
                onClick={() => onCite?.(Number(m[1]))}
                className="mx-0.5 -translate-y-0.5 rounded-sm bg-mark/70 px-1.5 align-baseline text-[11px] font-semibold text-black hover:bg-mark"
                aria-label={`Show source ${m[1]}`}
              >
                {m[1]}
              </button>
            )
          },
        }}
      >
        {md}
      </ReactMarkdown>
    </div>
  )
}

export function CitationItem({ c, open, onToggle }) {
  const long = c.excerpt.length > 220
  const shown = open || !long ? c.excerpt : `${c.excerpt.slice(0, 220)}…`
  return (
    <li id={c.number ? `cite-${c.number}` : undefined} className={`border-l-4 py-1 pl-3 ${c.verified ? 'border-mark' : 'border-warn'}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        {c.number != null && <span className="rounded-sm bg-mark/70 px-1.5 text-[11px] font-semibold text-black">{c.number}</span>}
        <span className="font-medium">{c.document_title}</span>
        {c.page_number != null && <span className="text-muted">page {c.page_number}</span>}
        {c.verified ? (
          <span className="inline-flex items-center gap-1 text-xs text-ok"><BadgeCheck className="h-3.5 w-3.5" aria-hidden="true" />Quote found in source</span>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs text-warn"><ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />Quote could not be verified</span>
        )}
      </div>
      <blockquote className="mt-1 text-sm leading-relaxed">
        <span className={c.verified ? 'hl' : 'hl-unverified'}>{shown}</span>
      </blockquote>
      <div className="mt-1 flex flex-wrap gap-3 text-xs">
        {long && <button className="text-brand underline" onClick={onToggle}>{open ? 'Show less' : 'Show more'}</button>}
        {c.document_id ? (
          <Link className="text-brand underline" to={`/documents/${c.document_id}${c.page_number ? `?page=${c.page_number}` : ''}`}>
            Open {c.page_number ? `page ${c.page_number}` : 'document'}
          </Link>
        ) : (
          <span className="inline-flex items-center gap-1 text-muted"><FileX2 className="h-3.5 w-3.5" aria-hidden="true" />Source document was deleted</span>
        )}
      </div>
    </li>
  )
}

export function CitationList({ citations, activeNumber }) {
  const [open, setOpen] = useState({})
  if (!citations?.length) return null
  return (
    <div className="mt-4">
      <h3 className="mb-2 text-sm font-semibold">Sources</h3>
      <ol className="space-y-3">
        {citations.map((c, i) => (
          <CitationItem key={c.chunk_id || i} c={c} open={open[i] || activeNumber === c.number}
            onToggle={() => setOpen((o) => ({ ...o, [i]: !o[i] }))} />
        ))}
      </ol>
    </div>
  )
}
