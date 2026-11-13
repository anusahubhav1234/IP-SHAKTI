import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { Spinner } from '../components/ui'

export function ProtectedRoute() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="grid h-screen place-items-center"><Spinner label="Loading your workspace" /></div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <Outlet />
}

export function AdminRoute() {
  const { isAdmin } = useAuth()
  return isAdmin ? <Outlet /> : <Navigate to="/dashboard" replace />
}

/** Login/register pages bounce signed-in users to the dashboard. */
export function GuestRoute() {
  const { user, loading } = useAuth()
  if (loading) return <div className="grid h-screen place-items-center"><Spinner label="Loading" /></div>
  return user ? <Navigate to="/dashboard" replace /> : <Outlet />
}
