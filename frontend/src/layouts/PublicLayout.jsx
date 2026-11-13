import { Link, Outlet } from 'react-router-dom'
import { Moon, Sun } from 'lucide-react'
import { Logo } from '../components/Logo'
import { useTheme } from '../contexts/ThemeContext'
import { useAuth } from '../contexts/AuthContext'

export default function PublicLayout() {
  const { theme, toggle } = useTheme()
  const { user } = useAuth()
  return (
    <div className="flex min-h-screen flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-4">
        <Link to="/" aria-label="IP-SAKTI Sahayaka home"><Logo /></Link>
        <nav className="flex items-center gap-2">
          <button className="btn btn-quiet !px-2" onClick={toggle} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
            {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          {user ? (
            <Link to="/dashboard" className="btn btn-primary">Open workspace</Link>
          ) : (
            <>
              <Link to="/login" className="btn btn-quiet">Sign in</Link>
              <Link to="/register" className="btn btn-primary">Create account</Link>
            </>
          )}
        </nav>
      </header>
      <main className="flex-1"><Outlet /></main>
      <footer className="mx-auto w-full max-w-6xl px-5 py-6 text-xs text-muted">
        B.Tech Information Technology major project, MLRITM. Answers come only from documents you upload.
      </footer>
    </div>
  )
}
