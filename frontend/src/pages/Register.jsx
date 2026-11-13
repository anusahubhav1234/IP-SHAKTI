import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { errorMessage } from '../services/api'
import { ErrorNote, Field } from '../components/ui'

export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ full_name: '', email: '', password: '', confirm: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const weak = form.password && (form.password.length < 8 || !/[A-Za-z]/.test(form.password) || !/\d/.test(form.password))
  const mismatch = form.confirm && form.confirm !== form.password

  async function submit(e) {
    e.preventDefault()
    if (weak || mismatch) return
    setBusy(true); setError('')
    try {
      await register({ full_name: form.full_name.trim(), email: form.email.trim(), password: form.password })
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(errorMessage(err, 'Could not create the account.'))
    } finally { setBusy(false) }
  }

  return (
    <div className="mx-auto w-full max-w-sm px-5 py-14">
      <h1 className="font-display text-3xl font-bold">Create your account</h1>
      <p className="mt-1 text-sm text-muted">Already registered? <Link className="text-brand underline" to="/login">Sign in</Link></p>
      <form onSubmit={submit} className="mt-8 space-y-4">
        <Field label="Full name" htmlFor="name"><input id="name" className="field" required minLength={2} maxLength={120} autoComplete="name" value={form.full_name} onChange={set('full_name')} /></Field>
        <Field label="Email" htmlFor="email"><input id="email" className="field" type="email" required autoComplete="email" value={form.email} onChange={set('email')} /></Field>
        <Field label="Password" htmlFor="password" hint="At least 8 characters, with a letter and a digit." error={weak ? 'Use at least 8 characters, including a letter and a digit.' : ''}>
          <input id="password" className="field" type="password" required maxLength={72} autoComplete="new-password" value={form.password} onChange={set('password')} />
        </Field>
        <Field label="Confirm password" htmlFor="confirm" error={mismatch ? 'The passwords do not match.' : ''}>
          <input id="confirm" className="field" type="password" required autoComplete="new-password" value={form.confirm} onChange={set('confirm')} />
        </Field>
        <ErrorNote>{error}</ErrorNote>
        <button className="btn btn-primary w-full" disabled={busy || weak || mismatch}>{busy ? 'Creating account…' : 'Create account'}</button>
      </form>
    </div>
  )
}
