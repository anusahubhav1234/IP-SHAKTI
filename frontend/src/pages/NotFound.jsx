import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="mx-auto max-w-xl px-5 py-24">
      <h1 className="font-display text-4xl font-bold">This page does not exist</h1>
      <p className="mt-3 text-muted">The link may be old, or the address may have a typo.</p>
      <Link to="/" className="btn btn-primary mt-6">Go to the home page</Link>
    </div>
  )
}
