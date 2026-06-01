import { Navigate, Route, Routes } from 'react-router-dom'
import { startTransition, useCallback, useEffect, useState } from 'react'
import { apiRequest } from './api/client'
import { SessionProvider, useSession } from './hooks/useSession.jsx'
import DashboardPage from './pages/DashboardPage'
import HomePage from './pages/HomePage'
import LandingPage from './pages/LandingPage'
import LegalPage from './pages/LegalPage'
import ProfilePage from './pages/ProfilePage'
import TripDetailPage from './pages/TripDetailPage'

const EMPTY_DASHBOARD = { recent_trips: [], saved_trips: [] }

function ProtectedRoute({ children }) {
  const { token } = useSession()
  if (!token) {
    return <Navigate replace to="/" />
  }
  return children
}

function AppRoutes() {
  const { token } = useSession()
  const [dashboard, setDashboard] = useState(EMPTY_DASHBOARD)
  const [profile, setProfile] = useState(null)
  const [loadingWorkspace, setLoadingWorkspace] = useState(false)

  // Stable identities (keyed on token) so pages can safely use these as effect
  // dependencies. Without useCallback they were re-created every render, which
  // turned the dependent effects into an unbounded fetch/render loop.
  const reloadDashboard = useCallback(async () => {
    if (!token) {
      setDashboard(EMPTY_DASHBOARD)
      return
    }
    const payload = await apiRequest('/trips', { token })
    startTransition(() => {
      setDashboard(payload)
    })
  }, [token])

  const reloadProfile = useCallback(async () => {
    if (!token) {
      setProfile(null)
      return
    }
    const payload = await apiRequest('/profile/me', { token })
    startTransition(() => {
      setProfile(payload)
    })
  }, [token])

  useEffect(() => {
    let ignore = false

    async function loadWorkspace() {
      if (!token) {
        setDashboard(EMPTY_DASHBOARD)
        setProfile(null)
        setLoadingWorkspace(false)
        return
      }

      setLoadingWorkspace(true)
      try {
        const [dashboardPayload, profilePayload] = await Promise.all([
          apiRequest('/trips', { token }),
          apiRequest('/profile/me', { token }),
        ])

        if (ignore) {
          return
        }

        startTransition(() => {
          setDashboard(dashboardPayload)
          setProfile(profilePayload)
        })
      } catch {
        if (ignore) {
          return
        }
        setDashboard(EMPTY_DASHBOARD)
        setProfile(null)
      } finally {
        if (!ignore) {
          setLoadingWorkspace(false)
        }
      }
    }

    loadWorkspace()

    return () => {
      ignore = true
    }
  }, [token])

  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/sign-in" element={<LandingPage initialMode="login" />} />
      <Route path="/sign-up" element={<LandingPage initialMode="register" />} />
      <Route path="/privacy" element={<LegalPage type="privacy" />} />
      <Route path="/terms" element={<LegalPage type="terms" />} />
      <Route
        path="/app"
        element={
          <DashboardPage
            dashboard={dashboard}
            loadingWorkspace={loadingWorkspace}
            profile={profile}
            reloadDashboard={reloadDashboard}
          />
        }
      />
      <Route
        path="/profile"
        element={
          <ProtectedRoute>
            <ProfilePage loadingWorkspace={loadingWorkspace} profile={profile} reloadProfile={reloadProfile} />
          </ProtectedRoute>
        }
      />
      <Route
        path="/trips/:tripId"
        element={
          <ProtectedRoute>
            <TripDetailPage />
          </ProtectedRoute>
        }
      />
    </Routes>
  )
}

export default function App() {
  return (
    <SessionProvider>
      <AppRoutes />
    </SessionProvider>
  )
}
