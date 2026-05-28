import { Navigate, Route, Routes } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { apiRequest } from './api/client'
import { SessionProvider, useSession } from './hooks/useSession.jsx'
import DashboardPage from './pages/DashboardPage'
import LandingPage from './pages/LandingPage'
import ProfilePage from './pages/ProfilePage'
import TripDetailPage from './pages/TripDetailPage'

function ProtectedRoute({ children }) {
  const { token } = useSession()
  if (!token) {
    return <Navigate replace to="/" />
  }
  return children
}

function AppRoutes() {
  const { token } = useSession()
  const [dashboard, setDashboard] = useState({ recent_trips: [], saved_trips: [] })
  const [profile, setProfile] = useState(null)

  async function reloadDashboard() {
    if (!token) {
      setDashboard({ recent_trips: [], saved_trips: [] })
      return
    }
    const payload = await apiRequest('/trips', { token })
    setDashboard(payload)
  }

  async function reloadProfile() {
    if (!token) {
      setProfile(null)
      return
    }
    const payload = await apiRequest('/profile/me', { token })
    setProfile(payload)
  }

  useEffect(() => {
    Promise.all([reloadDashboard(), reloadProfile()]).catch(() => {
      setDashboard({ recent_trips: [], saved_trips: [] })
      setProfile(null)
    })
  }, [token])

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <DashboardPage dashboard={dashboard} profile={profile} reloadDashboard={reloadDashboard} />
          </ProtectedRoute>
        }
      />
      <Route
        path="/profile"
        element={
          <ProtectedRoute>
            <ProfilePage profile={profile} reloadProfile={reloadProfile} />
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
