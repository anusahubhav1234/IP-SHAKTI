import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { FileUp, GitCompareArrows, MessageSquare } from 'lucide-react'
import { PageBody } from '../layouts/AppLayout'
import { EmptyState, ErrorNote, Figure, PageHeader, Section, Spinner, StatusBadge } from '../components/ui'
import { useAuth } from '../contexts/AuthContext'
import { useAsync } from '../hooks/useAsync'
import { useChartColors } from '../hooks/useChartColors'
import { analyticsApi, chatApi, documentsApi } from '../services/api'
import { languageName, timeAgo } from '../utils/format'

export default function Dashboard() {
  const { user } = useAuth()
  const colors = useChartColors()
  const overview = useAsync(() => analyticsApi.overview(), [])
  const docs = useAsync(() => documentsApi.list({ limit: 5 }), [])
  const convs = useAsync(() => chatApi.conversations({ limit: 5 }), [])
  const o = overview.data
  const first = user?.full_name?.split(' ')[0]

  const activity = (o?.activity || []).map((d) => ({ ...d, label: d.date.slice(5) }))
  const langs = Object.entries(o?.language_usage || {}).map(([k, v]) => ({ language: languageName(k), questions: v }))
  const noDocs = !docs.loading && docs.data?.total === 0

  return (
    <PageBody wide>
      <PageHeader
        title={`Welcome, ${first}`}
        subtitle="Ask a question, add a document, or pick up a recent conversation."
        actions={<>
          <Link className="btn btn-primary" to="/chat"><MessageSquare className="h-4 w-4" aria-hidden="true" />Ask a question</Link>
          <Link className="btn btn-quiet" to="/upload"><FileUp className="h-4 w-4" aria-hidden="true" />Upload</Link>
          <Link className="btn btn-quiet" to="/compare"><GitCompareArrows className="h-4 w-4" aria-hidden="true" />Compare</Link>
        </>}
      />
      <ErrorNote onRetry={overview.reload}>{overview.error}</ErrorNote>

      {overview.loading ? <Spinner label="Loading your numbers" /> : o && (
        <div className="flex flex-wrap gap-x-12 gap-y-6">
          <Figure label="Documents ready" value={o.documents.by_status.ready} note={o.documents.by_status.failed ? `${o.documents.by_status.failed} failed` : undefined} />
          <Figure label="Passages indexed" value={o.chunks} />
          <Figure label="Questions asked" value={o.messages.user} note={o.messages.insufficient_evidence ? `${o.messages.insufficient_evidence} without enough evidence` : undefined} />
          <Figure label="Conversations" value={o.conversations} />
        </div>
      )}

      {noDocs ? (
        <div className="mt-10">
          <EmptyState icon={FileUp} title="Start by adding a document"
            action={<Link className="btn btn-primary mt-2" to="/upload">Upload your first document</Link>}>
            PDF, Word, text and CSV files work. Once a document is ready you can ask questions about it.
          </EmptyState>
        </div>
      ) : (
        <div className="mt-10 grid gap-10 lg:grid-cols-2">
          <Section title="Recent documents" action={<Link className="text-sm text-brand underline" to="/documents">All documents</Link>}>
            {docs.loading ? <Spinner /> : (
              <ul className="divide-y divide-line">
                {docs.data?.items.map((d) => (
                  <li key={d.id} className="flex items-center justify-between gap-3 py-2.5">
                    <Link to={`/documents/${d.id}`} className="min-w-0 truncate font-medium hover:text-brand">{d.title}</Link>
                    <span className="flex shrink-0 items-center gap-3 text-xs text-muted">{timeAgo(d.uploaded_at)}<StatusBadge status={d.status} /></span>
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Section title="Recent conversations" action={<Link className="text-sm text-brand underline" to="/history">History</Link>}>
            {convs.loading ? <Spinner /> : convs.data?.items.length ? (
              <ul className="divide-y divide-line">
                {convs.data.items.map((c) => (
                  <li key={c.id} className="flex items-center justify-between gap-3 py-2.5">
                    <Link to={`/chat/${c.id}`} className="min-w-0 truncate font-medium hover:text-brand">{c.title}</Link>
                    <span className="shrink-0 text-xs text-muted">{timeAgo(c.updated_at)}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">No conversations yet. Your questions will appear here.</p>}
          </Section>
        </div>
      )}

      {o && (
        <div className="mt-10 grid gap-10 lg:grid-cols-[1.6fr_1fr]">
          <Section title="Your activity, last 14 days" hint="Questions asked and searches run.">
            <div className="h-56" role="img" aria-label="Bar chart of questions and searches per day">
              <ResponsiveContainer>
                <BarChart data={activity} margin={{ left: -20, right: 4 }}>
                  <CartesianGrid vertical={false} stroke={colors.line} />
                  <XAxis dataKey="label" tick={{ fill: colors.muted, fontSize: 11 }} tickLine={false} axisLine={false} interval={1} />
                  <YAxis allowDecimals={false} tick={{ fill: colors.muted, fontSize: 11 }} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ background: colors.surface, border: `1px solid ${colors.line}`, borderRadius: 6 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="chat" name="Questions" fill={colors.brand} radius={[3, 3, 0, 0]} />
                  <Bar dataKey="search" name="Searches" fill={colors.mark} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Section>
          <Section title="Question languages" hint="Detected from your questions.">
            {langs.length ? (
              <div className="h-56" role="img" aria-label="Bar chart of questions by language">
                <ResponsiveContainer>
                  <BarChart data={langs} layout="vertical" margin={{ left: 10, right: 10 }}>
                    <XAxis type="number" allowDecimals={false} hide />
                    <YAxis type="category" dataKey="language" width={70} tick={{ fill: colors.ink, fontSize: 12 }} tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={{ background: colors.surface, border: `1px solid ${colors.line}`, borderRadius: 6 }} />
                    <Bar dataKey="questions" fill={colors.brand} radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : <p className="text-sm text-muted">Nothing to show until you ask a question.</p>}
          </Section>
        </div>
      )}
    </PageBody>
  )
}
