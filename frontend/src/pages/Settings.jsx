import { PageBody } from '../layouts/AppLayout'
import { Field, PageHeader, Section } from '../components/ui'
import { usePrefs } from '../contexts/PrefsContext'
import { useTheme } from '../contexts/ThemeContext'
import { MODES } from '../utils/format'

export default function Settings() {
  const { theme, setTheme } = useTheme()
  const { prefs, setPrefs } = usePrefs()
  return (
    <PageBody>
      <PageHeader title="Settings" subtitle="Saved in this browser only." />
      <div className="max-w-md space-y-10">
        <Section title="Appearance">
          <div role="radiogroup" aria-label="Theme" className="flex gap-3">
            {['light', 'dark'].map((t) => <button key={t} role="radio" aria-checked={theme === t} onClick={() => setTheme(t)} className={`btn ${theme === t ? 'btn-primary' : 'btn-quiet'} capitalize`}>{t}</button>)}
          </div>
        </Section>
        <Section title="Retrieval">
          <div className="space-y-4">
            <Field label="Search mode" htmlFor="mode" hint={MODES.find((m) => m.value === prefs.mode)?.hint}>
              <select id="mode" className="field" value={prefs.mode} onChange={(e) => setPrefs({ mode: e.target.value })}>{MODES.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}</select>
            </Field>
            <Field label="Passages used per answer" htmlFor="topk">
              <select id="topk" className="field" value={prefs.topK} onChange={(e) => setPrefs({ topK: Number(e.target.value) })}>{[3, 5, 8, 10].map((n) => <option key={n}>{n}</option>)}</select>
            </Field>
          </div>
        </Section>
        <Section title="Privacy">
          <p className="text-sm text-muted">Your documents are visible only to you. Questions are sent to the language model service to write answers, together with the passages found. The audit log records actions, never the text of your questions. Your sign-in token is kept in this browser until you sign out.</p>
        </Section>
      </div>
    </PageBody>
  )
}
