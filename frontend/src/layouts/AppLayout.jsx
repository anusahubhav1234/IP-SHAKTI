import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { BarChart3, FileUp, FolderOpen, GitCompareArrows, History, LayoutDashboard, LogOut, Menu, MessageSquare, Moon, Settings, ShieldCheck, Sun, User, X } from 'lucide-react'
import { Logo } from '../components/Logo'
import { useAuth } from '../contexts/AuthContext'
import { useTheme } from '../contexts/ThemeContext'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/chat', label: 'Ask', icon: MessageSquare },
  { to: '/documents', label: 'Library', icon: FolderOpen },
  { to: '/upload', label: 'Upload', icon: FileUp },
  { to: '/compare', label: 'Compare', icon: GitCompareArrows },
  { to: '/history', label: 'History', icon: History },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
]

const linkCls = ({ isActive }) =>
  `flex items-center gap-3 rounded-field px-3 py-2 text-sm font-medium transition-colors ${isActive ? 'bg-brand/10 text-brand' : 'text-muted hover:bg-line/50 hover:text-ink'}`

export default function AppLayout() {
  const { user, logout, isAdmin } = useAuth()
  const { theme, toggle } = useTheme()
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  useEffect(() => setOpen(false), [location.pathname])

  const nav = (
    <nav className="flex h-full flex-col" aria-label="Main">
      <Link to="/dashboard" className="mb-6 px-3 pt-1"><Logo /></Link>
      <ul className="space-y-1">
        {[...NAV, ...(isAdmin ? [{ to: '/admin', label: 'Admin', icon: ShieldCheck }] : [])].map(({ to, label, icon: Icon }) => (
          <li key={to}><NavLink to={to} className={linkCls}><Icon className="h-4 w-4" aria-hidden="true" />{label}</NavLink></li>
        ))}
      </ul>
      <div className="mt-auto space-y-1 border-t border-line pt-3">
        <NavLink to="/profile" className={linkCls}><User className="h-4 w-4" aria-hidden="true" />
          <span className="min-w-0 truncate">{user?.full_name}</span></NavLink>
        <NavLink to="/settings" className={linkCls}><Settings className="h-4 w-4" aria-hidden="true" />Settings</NavLink>
        <button className={`${linkCls({ isActive: false })} w-full`} onClick={toggle}>
          {theme === 'dark' ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
          {theme === 'dark' ? 'Light theme' : 'Dark theme'}
        </button>
        <button className={`${linkCls({ isActive: false })} w-full`} onClick={async () => { await logout(); navigate('/') }}>
          <LogOut className="h-4 w-4" aria-hidden="true" />Sign out
        </button>
      </div>
    </nav>
  )

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="hidden w-56 shrink-0 border-r border-line bg-surface p-3 lg:block">{nav}</aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <button className="absolute inset-0 bg-black/50" aria-label="Close menu" onClick={() => setOpen(false)} />
          <aside className="relative h-full w-64 bg-surface p-3 shadow-xl">{nav}</aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-line bg-surface px-4 py-2 lg:hidden">
          <button className="btn btn-quiet !px-2" onClick={() => setOpen(true)} aria-label="Open menu"><Menu className="h-4 w-4" /></button>
          <Logo className="!text-base" />
          <span className="w-9" />
        </div>
        <main id="main" className="min-h-0 flex-1 overflow-y-auto"><Outlet /></main>
      </div>
    </div>
  )
}

export function PageBody({ children, wide = false }) {
  return <div className={`mx-auto w-full px-5 py-8 sm:px-8 ${wide ? 'max-w-6xl' : 'max-w-4xl'}`}>{children}</div>
}
