import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiRequest } from '../api/client'
import AppShell from '../components/AppShell'
import GlobeLoader from '../components/GlobeLoader'
import IntakeForm from '../components/IntakeForm'
import { OPTIONS_LOADER } from '../lib/loaderCopy'
import { useSession } from '../hooks/useSession.jsx'
import { tripWindow } from '../lib/format'

function EmptyState({ title, body }) {
  return (
    <article className="empty-state-card">
      <strong>{title}</strong>
      <p>{body}</p>
    </article>
  )
}

// Compact, single trip row: the row links to the trip; secondary actions live
// behind an overflow menu so the row stays one tidy line of fixed height.
function TripRow({ to, title, meta, menuItems }) {
  const [open, setOpen] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    if (!open) {
      return undefined
    }
    function handlePointer(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setOpen(false)
      }
    }
    function handleKey(event) {
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handlePointer)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handlePointer)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  const hasMenu = Boolean(menuItems && menuItems.length)

  return (
    <div className="trip-row">
      <Link className="trip-row-main" to={to}>
        <span className="trip-row-title">{title}</span>
        <span className="trip-row-meta">{meta}</span>
      </Link>
      <div className="trip-row-trailing">
        {hasMenu ? (
          <div className="trip-row-menu" ref={menuRef}>
            <button
              aria-expanded={open}
              aria-haspopup="menu"
              aria-label="More actions"
              className="trip-row-menu-trigger"
              onClick={() => setOpen((value) => !value)}
              type="button"
            >
              ⋯
            </button>
            {open ? (
              <div className="trip-row-menu-pop" role="menu">
                {menuItems.map((item) => (
                  <button
                    className="trip-row-menu-item"
                    disabled={item.disabled}
                    key={item.label}
                    onClick={() => {
                      setOpen(false)
                      item.onClick()
                    }}
                    role="menuitem"
                    type="button"
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          <span aria-hidden="true" className="trip-row-chevron">
            ›
          </span>
        )}
      </div>
    </div>
  )
}

function isPastTrip(trip) {
  const end = new Date(trip.end_date)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return end < today
}

export default function DashboardPage({ dashboard, loadingWorkspace, profile, reloadDashboard }) {
  const navigate = useNavigate()
  const { token } = useSession()
  const [submitting, setSubmitting] = useState(false)
  const [duplicatingTripId, setDuplicatingTripId] = useState('')
  const [prefillTrip, setPrefillTrip] = useState(null)
  const [error, setError] = useState('')
  const [savedTab, setSavedTab] = useState('upcoming')

  const upcomingTrips = useMemo(
    () => dashboard.saved_trips.filter((trip) => !isPastTrip(trip)),
    [dashboard.saved_trips],
  )
  const pastTrips = useMemo(
    () => dashboard.saved_trips.filter((trip) => isPastTrip(trip)),
    [dashboard.saved_trips],
  )
  const hasPendingTrips = useMemo(
    () => dashboard.recent_trips.some((trip) => ['planning', 'building_itinerary'].includes(trip.status)),
    [dashboard.recent_trips],
  )
  const recentTrips = useMemo(() => dashboard.recent_trips.slice(0, 3), [dashboard.recent_trips])
  const planningHealth = profile?.home_airport ? 'Ready' : 'Incomplete'
  const showWorkspaceLoading = loadingWorkspace && !dashboard.recent_trips.length && !dashboard.saved_trips.length && !profile
  const savedCount = dashboard.saved_trips.length
  const activeSavedTrips = savedTab === 'past' ? pastTrips : upcomingTrips

  const intakeDefaults = useMemo(
    () =>
      prefillTrip
        ? {
            origin: prefillTrip.origin,
            start_date: prefillTrip.start_date,
            end_date: prefillTrip.end_date,
            destination_candidates: prefillTrip.destination_candidates,
            trip_style: prefillTrip.trip_style.split(' Traveler profile interests:')[0],
            budget_range: prefillTrip.budget_range || profile?.budget_preference || 'Mid-range',
            traveler_count: prefillTrip.traveler_count,
            pace_preference: prefillTrip.pace_preference || profile?.pace_preference || 'Balanced',
          }
        : {
            origin: profile?.home_airport || '',
            budget_range: profile?.budget_preference || 'Mid-range',
            pace_preference: profile?.pace_preference || 'Balanced',
          },
    [prefillTrip, profile],
  )

  async function handleCreateTrip(payload) {
    setSubmitting(true)
    setError('')
    try {
      const trip = await apiRequest('/trips', {
        method: 'POST',
        body: payload,
        token,
      })
      setPrefillTrip(null)
      navigate(`/trips/${trip.id}`)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDuplicateTrip(tripId) {
    setDuplicatingTripId(tripId)
    setError('')
    try {
      const trip = await apiRequest(`/trips/${tripId}/duplicate`, {
        method: 'POST',
        token,
      })
      navigate(`/trips/${trip.id}`)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setDuplicatingTripId('')
    }
  }

  useEffect(() => {
    if (!hasPendingTrips) {
      return undefined
    }
    const intervalId = window.setInterval(() => {
      reloadDashboard().catch(() => {})
    }, 3000)
    return () => window.clearInterval(intervalId)
  }, [hasPendingTrips, reloadDashboard])

  useEffect(() => {
    reloadDashboard().catch(() => {})
  }, [reloadDashboard])

  return (
    <AppShell
      compactHeader
      title="Plan the trip. Keep the details together."
      subtitle="Build a route shortlist, reuse saved trips, and keep the next step clear."
    >
      <section className="workspace-overview" aria-label="Workspace summary">
        <article className="surface-card stat-card">
          <p className="eyebrow">Profile</p>
          <strong>{planningHealth}</strong>
          <span>{profile?.home_airport ? `Home airport: ${profile.home_airport}` : 'Add a home airport.'}</span>
        </article>
        <article className="surface-card stat-card">
          <p className="eyebrow">Saved trips</p>
          <strong>{dashboard.saved_trips.length}</strong>
          <span>{upcomingTrips.length} upcoming</span>
        </article>
        <article className="surface-card stat-card">
          <p className="eyebrow">Recent runs</p>
          <strong>{dashboard.recent_trips.length}</strong>
          <span>{hasPendingTrips ? 'Planner active' : 'No active jobs'}</span>
        </article>
        <article className="surface-card stat-card stat-card-action">
          <div>
            <p className="eyebrow">Defaults</p>
            <strong>{profile?.home_airport || 'Unset'}</strong>
            <span>{profile?.budget_preference || 'Mid-range'} · {profile?.pace_preference || 'Balanced'}</span>
          </div>
          <Link className="secondary-button stat-card-link" to="/profile">
            Open profile
          </Link>
        </article>
      </section>

      <div className="dashboard-grid">
        <div className="dashboard-main">
          {showWorkspaceLoading ? (
            <section className="surface-card planner-notice" aria-live="polite">
              <p className="eyebrow">Syncing workspace</p>
              <h2>Pulling in your latest profile, saved trips, and planning history.</h2>
              <p>The workspace will fill in as soon as the latest data is ready.</p>
            </section>
          ) : null}

          {submitting ? (
            <GlobeLoader fullscreen messages={OPTIONS_LOADER.messages} showTips title={OPTIONS_LOADER.title} />
          ) : null}
          <IntakeForm
            initialValues={intakeDefaults}
            onClearPreset={() => setPrefillTrip(null)}
            onSubmit={handleCreateTrip}
            showPresetBanner={Boolean(prefillTrip)}
            submitting={submitting}
          />
          {error ? <p className="inline-error">{error}</p> : null}
        </div>

        <aside className="dashboard-sidebar">
          <section className="surface-card">
            <div className="sidebar-section-head">
              <div>
                <p className="eyebrow">Saved trips</p>
                <h2>{savedCount ? 'Trip library' : 'No saved trips yet'}</h2>
              </div>
              {savedCount ? (
                <div className="panel-switch saved-tabs" role="tablist" aria-label="Saved trips filter">
                  <button
                    aria-selected={savedTab === 'upcoming'}
                    className={savedTab === 'upcoming' ? 'active' : ''}
                    onClick={() => setSavedTab('upcoming')}
                    role="tab"
                    type="button"
                  >
                    Upcoming · {upcomingTrips.length}
                  </button>
                  <button
                    aria-selected={savedTab === 'past'}
                    className={savedTab === 'past' ? 'active' : ''}
                    onClick={() => setSavedTab('past')}
                    role="tab"
                    type="button"
                  >
                    Past · {pastTrips.length}
                  </button>
                </div>
              ) : null}
            </div>

            <div className="trip-row-list">
              {activeSavedTrips.length ? (
                activeSavedTrips.map((trip) => (
                  <TripRow
                    key={trip.id}
                    menuItems={
                      savedTab === 'past'
                        ? [{ label: 'Plan again', onClick: () => setPrefillTrip(trip) }]
                        : [
                            { label: 'Use as starting point', onClick: () => setPrefillTrip(trip) },
                            {
                              label: duplicatingTripId === trip.id ? 'Duplicating…' : 'Duplicate',
                              disabled: duplicatingTripId === trip.id,
                              onClick: () => handleDuplicateTrip(trip.id),
                            },
                          ]
                    }
                    meta={
                      savedTab === 'past'
                        ? `${tripWindow(trip.start_date, trip.end_date)} · ${trip.saved_trip?.confirmed_booking_count || 0} confirmed`
                        : `${tripWindow(trip.start_date, trip.end_date)} · ${trip.status}`
                    }
                    title={trip.destination_candidates.join(' · ')}
                    to={`/trips/${trip.id}`}
                  />
                ))
              ) : savedTab === 'past' ? (
                <EmptyState
                  title="Completed trips stay here for easy reference."
                  body="Once a trip has passed, you can still reopen it or use it as the base for another itinerary."
                />
              ) : (
                <EmptyState
                  title="Your next saved itinerary will show up here."
                  body="Generate a route shortlist, pick the strongest option, and save it to keep the planning history together."
                />
              )}
            </div>
          </section>

          <section className="surface-card">
            <div className="sidebar-section-head">
              <div>
                <p className="eyebrow">Recent plans</p>
                <h2>{dashboard.recent_trips.length ? 'Recent activity' : 'No planning runs yet'}</h2>
              </div>
            </div>
            <div className="trip-row-list">
              {recentTrips.length ? (
                recentTrips.map((trip) => (
                  <TripRow
                    key={trip.id}
                    meta={`${tripWindow(trip.start_date, trip.end_date)} · ${trip.status}`}
                    title={trip.destination_candidates.join(' · ')}
                    to={`/trips/${trip.id}`}
                  />
                ))
              ) : (
                <EmptyState
                  title="New planning runs will appear here."
                  body="Once you submit your first trip brief, you will be able to reopen the research even before saving it."
                />
              )}
            </div>
          </section>
        </aside>
      </div>
    </AppShell>
  )
}
