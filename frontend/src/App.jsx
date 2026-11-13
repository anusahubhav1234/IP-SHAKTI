import { Suspense, lazy } from 'react'
import { Route, Routes } from 'react-router-dom'
import PublicLayout from './layouts/PublicLayout'
import AppLayout from './layouts/AppLayout'
import { AdminRoute, GuestRoute, ProtectedRoute } from './routes/Guards'
import { Spinner } from './components/ui'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Register from './pages/Register'
import NotFound from './pages/NotFound'

// Pages with charts or heavy views load on demand to keep the first screen fast.
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Chat = lazy(() => import('./pages/Chat'))
const Library = lazy(() => import('./pages/Library'))
const Upload = lazy(() => import('./pages/Upload'))
const DocumentDetail = lazy(() => import('./pages/DocumentDetail'))
const Compare = lazy(() => import('./pages/Compare'))
const HistoryPage = lazy(() => import('./pages/History'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Admin = lazy(() => import('./pages/Admin'))
const Profile = lazy(() => import('./pages/Profile'))
const SettingsPage = lazy(() => import('./pages/Settings'))

export default function App() {
  return (
    <Suspense fallback={<div className="grid h-screen place-items-center"><Spinner label="Loading" /></div>}>
      <Routes>
        <Route element={<PublicLayout />}>
          <Route path="/" element={<Landing />} />
          <Route element={<GuestRoute />}>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
          </Route>
        </Route>

        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/chat/:conversationId" element={<Chat />} />
            <Route path="/documents" element={<Library />} />
            <Route path="/documents/:id" element={<DocumentDetail />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route element={<AdminRoute />}>
              <Route path="/admin" element={<Admin />} />
            </Route>
          </Route>
        </Route>

        <Route element={<PublicLayout />}>
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
