import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiRequest } from '../api/client'
import AppShell from '../components/AppShell'
import IntakeForm from '../components/IntakeForm'
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
  const planningHealth = profile?.home_airport ? 'Ready to plan' : 'Add profile defaults'
  const showWorkspaceLoading = loadingWorkspace && !dashboard.recent_trips.length && !dashboard.saved_trips.length && !profile

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

  return (
    <AppShell
      title="Plan a trip with structure, tradeoffs, and a clear next step."
      subtitle="Build a fresh route shortlist, reuse a saved trip as your starting point, and keep every planning decision in one organized workspace."
    >
      <div className="dashboard-grid">
        <div className="dashboard-main">
          <section className="stats-grid" aria-label="Workspace summary">
            <article className="surface-card stat-card">
              <p className="eyebrow">Profile readiness</p>
              <strong>{planningHealth}</strong>
              <span>{profile?.home_airport ? `Home airport: ${profile.home_airport}` : 'Add defaults to speed up new trip briefs.'}</span>
            </article>
            <article className="surface-card stat-card">
              <p className="eyebrow">Saved trips</p>
              <strong>{dashboard.saved_trips.length}</strong>
              <span>{upcomingTrips.length} upcoming itineraries ready to reopen.</span>
            </article>
            <article className="surface-card stat-card">
              <p className="eyebrow">Recent planning runs</p>
              <strong>{dashboard.recent_trips.length}</strong>
              <span>{prefillTrip ? 'Using a saved trip as your current starting point.' : 'Every request stays available for follow-up.'}</span>
            </article>
          </section>

          {showWorkspaceLoading ? (
            <section className="surface-card planner-notice" aria-live="polite">
              <p className="eyebrow">Syncing workspace</p>
              <h2>Pulling in your latest profile, saved trips, and planning history.</h2>
              <p>The workspace will fill in as soon as the latest data is ready.</p>
            </section>
          ) : null}

          {submitting ? (
            <section className="surface-card planner-status-card" aria-live="polite">
              <p className="eyebrow">Planning run in progress</p>
              <h2>Creating your trip workspace and queueing the planner.</h2>
              <p>
                Trip Architect is saving your brief first, then it will generate structured route options in the
                background so you can follow the job from the trip workspace.
              </p>
              <div className="status-step-list">
                <div className="status-step">
                  <strong>1. Workspace</strong>
                  <span>Persisting the trip request and traveler defaults.</span>
                </div>
                <div className="status-step">
                  <strong>2. Planning agents</strong>
                  <span>Queueing routing, research, and budget generation in the background.</span>
                </div>
                <div className="status-step">
                  <strong>3. Trip workspace</strong>
                  <span>You’ll land on the trip page as soon as the workspace is ready.</span>
                </div>
              </div>
            </section>
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
            <div className="section-header">
              <div>
                <p className="eyebrow">Traveler defaults</p>
                <h2>{profile?.home_airport || 'Add profile'}</h2>
              </div>
              <p>Save planning preferences once, then reuse them across every new itinerary.</p>
            </div>
            <Link className="secondary-button inline-link-button" to="/profile">
              Open profile
            </Link>
          </section>

          <section className="surface-card">
            <div className="section-header">
              <div>
                <p className="eyebrow">Saved trips</p>
                <h2>{dashboard.saved_trips.length ? 'Trip library' : 'No saved trips yet'}</h2>
              </div>
              <p>Upcoming trips stay separate from completed itineraries so the workspace stays useful over time.</p>
            </div>

            <div className="trip-bucket">
              <p className="eyebrow">Upcoming</p>
              <div className="trip-summary-list">
                {upcomingTrips.length ? (
                  upcomingTrips.map((trip) => (
                    <article className="trip-summary-card trip-summary-block" key={trip.id}>
                      <div>
                        <strong>{trip.destination_candidates.join(' · ')}</strong>
                        <p>{trip.origin}</p>
                      </div>
                      <div className="trip-summary-meta">
                        <span>{tripWindow(trip.start_date, trip.end_date)}</span>
                        <small>{trip.status}</small>
                      </div>
                      <div className="trip-card-actions">
                        <Link className="secondary-button inline-link-button" to={`/trips/${trip.id}`}>
                          Continue
                        </Link>
                        <button className="ghost-button" onClick={() => setPrefillTrip(trip)} type="button">
                          Use as starting point
                        </button>
                        <button
                          className="ghost-button"
                          disabled={duplicatingTripId === trip.id}
                          onClick={() => handleDuplicateTrip(trip.id)}
                          type="button"
                        >
                          {duplicatingTripId === trip.id ? 'Duplicating...' : 'Duplicate'}
                        </button>
                      </div>
                    </article>
                  ))
                ) : (
                  <EmptyState
                    title="Your next saved itinerary will show up here."
                    body="Generate a route shortlist, pick the strongest option, and save it to keep the planning history together."
                  />
                )}
              </div>
            </div>

            <div className="trip-bucket">
              <p className="eyebrow">Past trips</p>
              <div className="trip-summary-list">
                {pastTrips.length ? (
                  pastTrips.map((trip) => (
                    <article className="trip-summary-card trip-summary-block" key={trip.id}>
                      <div>
                        <strong>{trip.destination_candidates.join(' · ')}</strong>
                        <p>{trip.origin}</p>
                      </div>
                      <div className="trip-summary-meta">
                        <span>{tripWindow(trip.start_date, trip.end_date)}</span>
                        <small>{trip.saved_trip?.confirmed_booking_count || 0} confirmed</small>
                      </div>
                      <div className="trip-card-actions">
                        <Link className="secondary-button inline-link-button" to={`/trips/${trip.id}`}>
                          Reopen
                        </Link>
                        <button className="ghost-button" onClick={() => setPrefillTrip(trip)} type="button">
                          Plan again
                        </button>
                      </div>
                    </article>
                  ))
                ) : (
                  <EmptyState
                    title="Completed trips stay here for easy reference."
                    body="Once a trip has passed, you can still reopen it or use it as the base for another itinerary."
                  />
                )}
              </div>
            </div>
          </section>

          <section className="surface-card">
            <div className="section-header">
              <div>
                <p className="eyebrow">Recent plans</p>
                <h2>{dashboard.recent_trips.length ? 'Recent planning activity' : 'No planning runs yet'}</h2>
              </div>
              <p>Every request stays re-openable, even before it becomes a saved itinerary.</p>
            </div>
            <div className="trip-summary-list">
              {dashboard.recent_trips.length ? (
                dashboard.recent_trips.slice(0, 4).map((trip) => (
                  <Link className="trip-summary-card" key={trip.id} to={`/trips/${trip.id}`}>
                    <div>
                      <strong>{trip.destination_candidates.join(' · ')}</strong>
                      <p>{trip.origin}</p>
                    </div>
                    <div className="trip-summary-meta">
                      <span>{tripWindow(trip.start_date, trip.end_date)}</span>
                      <small>{trip.status}</small>
                    </div>
                  </Link>
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
