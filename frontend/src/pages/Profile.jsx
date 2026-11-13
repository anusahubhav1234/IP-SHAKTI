import { useState } from 'react'
import { PageBody } from '../layouts/AppLayout'
import { LanguageSelect } from '../components/LanguageSelect'
import { ErrorNote, Field, Notice, PageHeader, Section } from '../components/ui'
import { useAuth } from '../contexts/AuthContext'
import { authApi, errorMessage } from '../services/api'

export default function Profile() {
  const { user, setUser } = useAuth()
  const [name, setName] = useState(user.full_name)
  const [lang, setLang] = useState(user.preferred_language)
  const [msg, setMsg] = useState(''); const [err, setErr] = useState('')
  const [cur, setCur] = useState(''); const [next, setNext] = useState('')
  const [pmsg, setPmsg] = useState(''); const [perr, setPerr] = useState('')

  async function save(e) {
    e.preventDefault(); setMsg(''); setErr('')
    try { setUser(await authApi.updateProfile({ full_name: name, preferred_language: lang })); setMsg('Profile saved.') } catch (x) { setErr(errorMessage(x)) }
  }
  async function change(e) {
    e.preventDefault(); setPmsg(''); setPerr('')
    try { await authApi.changePassword({ current_password: cur, new_password: next }); setCur(''); setNext(''); setPmsg('Password changed.') } catch (x) { setPerr(errorMessage(x)) }
  }
  return (
    <PageBody>
      <PageHeader title="Profile" subtitle={user.email} />
      <div className="space-y-10">
        <Section title="Details">
          <form onSubmit={save} className="max-w-md space-y-4">
            <Field label="Full name" htmlFor="fn"><input id="fn" className="field" required minLength={2} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Preferred answer language" htmlFor="pl"><LanguageSelect id="pl" value={lang} onChange={setLang} label="" /></Field>
            <ErrorNote>{err}</ErrorNote>{msg && <Notice>{msg}</Notice>}
            <button className="btn btn-primary">Save</button>
          </form>
        </Section>
        <Section title="Change password">
          <form onSubmit={change} className="max-w-md space-y-4">
            <Field label="Current password" htmlFor="cp"><input id="cp" type="password" autoComplete="current-password" className="field" required value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
            <Field label="New password" htmlFor="np" hint="At least 8 characters with a letter and a digit."><input id="np" type="password" autoComplete="new-password" className="field" required minLength={8} value={next} onChange={(e) => setNext(e.target.value)} /></Field>
            <ErrorNote>{perr}</ErrorNote>{pmsg && <Notice>{pmsg}</Notice>}
            <button className="btn btn-primary">Change password</button>
          </form>
        </Section>
      </div>
    </PageBody>
  )
}
