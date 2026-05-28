import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiRequest } from '../api/client'
import AppShell from '../components/AppShell'
import InventoryPanel from '../components/InventoryPanel'
import OptionCard from '../components/OptionCard'
import Timeline from '../components/Timeline'
import { useSession } from '../hooks/useSession.jsx'
import { tripWindow } from '../lib/format'

const TRIP_TABS = ['Options', 'Itinerary', 'Stays', 'Travel']

export default function TripDetailPage() {
  const { tripId } = useParams()
  const { token } = useSession()
  const [trip, setTrip] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [selectingOptionId, setSelectingOptionId] = useState('')
  const [bookingSavingKey, setBookingSavingKey] = useState('')
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('Options')

  async function loadTrip({ silent = false } = {}) {
    try {
      const payload = await apiRequest(`/trips/${tripId}`, { token })
      setTrip(payload)
      if (!silent) {
        setError('')
      }
    } catch (loadError) {
      if (!silent) {
        setError(loadError.message)
      }
    } finally {
      if (!silent) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    loadTrip()
  }, [token, tripId])

  const selectedOption = useMemo(
    () => trip?.options.find((option) => option.id === trip.selected_option_id) || null,
    [trip],
  )
  const itinerary = trip?.itineraries[0] || null
  const latestOptionsRun = useMemo(
    () => [...(trip?.agent_runs || [])].reverse().find((run) => run.kind === 'options') || null,
    [trip],
  )
  const latestItineraryRun = useMemo(
    () => [...(trip?.agent_runs || [])].reverse().find((run) => run.kind === 'itinerary') || null,
    [trip],
  )
  const fallbackReason =
    latestItineraryRun?.output_payload?.fallback_reason || latestOptionsRun?.output_payload?.fallback_reason || ''
  const failedReason = latestItineraryRun?.output_payload?.error || latestOptionsRun?.output_payload?.error || ''
  const isPlanningOptions = trip?.status === 'planning'
  const isBuildingItinerary = trip?.status === 'building_itinerary'
  const isPending = isPlanningOptions || isBuildingItinerary
  const showPlanningScreen = isPlanningOptions && !trip?.options.length
  const requiresSelectedOption = activeTab !== 'Options'

  useEffect(() => {
    if (!isPending) {
      return undefined
    }
    const intervalId = window.setInterval(() => {
      loadTrip({ silent: true })
    }, 2500)
    return () => window.clearInterval(intervalId)
  }, [isPending, tripId, token])

  async function handleSelect(optionId) {
    setSelectingOptionId(optionId)
    try {
      const payload = await apiRequest(`/trips/${trip.id}/select-option/${optionId}`, {
        method: 'POST',
        token,
      })
      setTrip(payload)
    } catch (selectError) {
      setError(selectError.message)
    } finally {
      setSelectingOptionId('')
    }
  }

  async function handleSave() {
    if (!trip) {
      return
    }
    setSaving(true)
    try {
      const payload = await apiRequest(`/trips/${trip.id}/save`, {
        method: 'POST',
        token,
        body: {
          label: `${trip.destination_candidates.join(' + ')} plan`,
          notes: 'Saved from the MVP dashboard.',
        },
      })
      setTrip(payload)
    } catch (saveError) {
      setError(saveError.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleBookingSelection(bookingType, optionId, selectionState) {
    setBookingSavingKey(`${bookingType}:${optionId}`)
    setError('')
    try {
      const payload = await apiRequest(`/trips/${trip.id}/booking-selection`, {
        method: 'POST',
        token,
        body: {
          booking_type: bookingType,
          option_id: optionId,
          selection_state: selectionState,
        },
      })
      setTrip(payload)
    } catch (selectionError) {
      setError(selectionError.message)
    } finally {
      setBookingSavingKey('')
    }
  }

  if (loading) {
    return <main className="loading-state">Loading trip workspace...</main>
  }

  if (!trip) {
    return (
      <main className="loading-state">
        <p>{error || 'Trip not found.'}</p>
        <Link className="primary-button" to="/app">
          Return to dashboard
        </Link>
      </main>
    )
  }

  if (showPlanningScreen) {
    return (
      <AppShell
        title={trip.destination_candidates.join(' · ')}
        subtitle={`${trip.origin} · ${tripWindow(trip.start_date, trip.end_date)} · ${trip.status}`}
        actions={
          <button className="primary-button" disabled={saving} onClick={handleSave} type="button">
            {trip.saved_trip ? 'Saved to dashboard' : saving ? 'Saving...' : 'Save trip'}
          </button>
        }
      >
        {error ? <p className="inline-error">{error}</p> : null}
        <section className="surface-card planner-wait-card" aria-live="polite">
          <p className="eyebrow">Planning run in progress</p>
          <h2>Please wait, suggestions are being generated.</h2>
          <p>
            Trip Architect is comparing routes, rough budgets, and tradeoffs now. This page refreshes automatically
            while the options run finishes.
          </p>
          <div className="status-step-list">
            <div className="status-step">
              <strong>1. Intake agent</strong>
              <span>Normalizing dates, origin, traveler count, and trip intent.</span>
            </div>
            <div className="status-step">
              <strong>2. Routing + research agents</strong>
              <span>Evaluating feasible stop combinations and destination fit.</span>
            </div>
            <div className="status-step">
              <strong>3. Budget + planner agents</strong>
              <span>Ranking the strongest trip options for this brief.</span>
            </div>
          </div>
        </section>
      </AppShell>
    )
  }

  return (
    <AppShell
      title={trip.destination_candidates.join(' · ')}
      subtitle={`${trip.origin} · ${tripWindow(trip.start_date, trip.end_date)} · ${trip.status}`}
      actions={
        <button className="primary-button" disabled={saving} onClick={handleSave} type="button">
          {trip.saved_trip ? 'Saved to dashboard' : saving ? 'Saving...' : 'Save trip'}
        </button>
      }
    >
      {error ? <p className="inline-error">{error}</p> : null}

      {fallbackReason ? (
        <section className="surface-card planner-notice" aria-live="polite">
          <p className="eyebrow">Planner status</p>
          <h2>Using the structured fallback planner for this trip.</h2>
          <p>{fallbackReason}</p>
        </section>
      ) : null}

      {trip.status === 'failed' ? (
        <section className="surface-card planner-notice planner-error" aria-live="polite">
          <p className="eyebrow">Planner status</p>
          <h2>Trip generation hit an error before the workspace was completed.</h2>
          <p>{failedReason || 'The planner stopped unexpectedly. You can return to the dashboard and try again.'}</p>
        </section>
      ) : null}

      <section className="surface-card summary-strip">
        <div>
          <p className="eyebrow">Trip brief</p>
          <h2>{trip.trip_style}</h2>
        </div>
        <div className="summary-metadata">
          <span>{trip.traveler_count} travelers</span>
          <span>{trip.budget_range || 'Flexible budget'}</span>
          <span>{trip.planning_mode} planning mode</span>
          <span>{trip.confirmed_bookings.length} saved bookings</span>
        </div>
      </section>

      <div className="trip-tab-bar" role="tablist" aria-label="Trip workspace sections">
        {TRIP_TABS.map((tab) => (
          <button
            aria-selected={activeTab === tab}
            className={`trip-tab ${activeTab === tab ? 'active' : ''}`}
            key={tab}
            onClick={() => setActiveTab(tab)}
            role="tab"
            type="button"
          >
            {tab}
          </button>
        ))}
      </div>

      {isBuildingItinerary || selectingOptionId ? (
        <section className="surface-card planner-status-card" aria-live="polite">
          <p className="eyebrow">Detailed planning in progress</p>
          <h2>Expanding the selected route into a day-by-day trip workspace.</h2>
          <p>
            Trip Architect is building itinerary structure, neighborhood guidance, and booking discovery for the
            selected option.
          </p>
          <div className="status-step-list">
            <div className="status-step">
              <strong>1. Research agent</strong>
              <span>Checking destination fit, seasonality, and logistics context.</span>
            </div>
            <div className="status-step">
              <strong>2. Itinerary agent</strong>
              <span>Drafting daily morning, afternoon, and evening suggestions.</span>
            </div>
            <div className="status-step">
              <strong>3. Booking discovery agent</strong>
              <span>Preparing flight and stay options that match the chosen route.</span>
            </div>
          </div>
        </section>
      ) : null}

      {requiresSelectedOption && !selectedOption ? (
        <section className="surface-card planner-notice">
          <p className="eyebrow">{activeTab}</p>
          <h2>Please select a trip option before continuing.</h2>
          <p>Open the Options tab, pick the route you want, and then Trip Architect will unlock the detailed plan.</p>
        </section>
      ) : null}

      {activeTab === 'Options' ? (
        <>
          <section className="options-grid" role="tabpanel" aria-label="Trip options">
            {trip.options.map((option) => (
              <OptionCard
                active={selectedOption?.id === option.id}
                key={option.id}
                onSelect={handleSelect}
                option={option}
                selecting={selectingOptionId === option.id}
              />
            ))}
          </section>

          {!trip.options.length && !isPlanningOptions && trip.status !== 'failed' ? (
            <section className="surface-card planner-notice">
              <p className="eyebrow">Trip options</p>
              <h2>Route options will appear here as soon as planning finishes.</h2>
              <p>This workspace refreshes automatically while the planning job is still running.</p>
            </section>
          ) : null}
        </>
      ) : null}

      {activeTab === 'Itinerary' && selectedOption ? (
        <section role="tabpanel" aria-label="Trip itinerary">
          {itinerary ? <Timeline itinerary={itinerary} /> : null}

          {!itinerary && !isBuildingItinerary && trip.status !== 'failed' ? (
            <section className="surface-card planner-notice">
              <p className="eyebrow">Itinerary detail</p>
              <h2>The selected route is saved. A detailed itinerary will appear here after expansion runs.</h2>
              <p>Choose the route you want to deepen and Trip Architect will build the daily plan and booking discovery.</p>
            </section>
          ) : null}
        </section>
      ) : null}

      {activeTab === 'Stays' && selectedOption ? (
        <section role="tabpanel" aria-label="Trip stays">
          <InventoryPanel
            bookingSavingKey={bookingSavingKey}
            confirmedBookings={trip.confirmed_bookings}
            flights={trip.flight_options}
            hotels={trip.hotel_options}
            mode="hotels"
            onUpdateBookingSelection={handleBookingSelection}
          />
        </section>
      ) : null}

      {activeTab === 'Travel' && selectedOption ? (
        <section role="tabpanel" aria-label="Trip travel">
          <InventoryPanel
            bookingSavingKey={bookingSavingKey}
            confirmedBookings={trip.confirmed_bookings}
            flights={trip.flight_options}
            hotels={trip.hotel_options}
            mode="flights"
            onUpdateBookingSelection={handleBookingSelection}
          />
        </section>
      ) : null}

      <section className="surface-card">
        <div className="section-header">
          <div>
            <p className="eyebrow">Agent observability</p>
            <h2>How the plan was assembled</h2>
          </div>
          <p>Each run distinguishes traveler input, inferred recommendations, and estimated price assumptions.</p>
        </div>

        <div className="agent-run-list">
          {trip.agent_runs.map((run) => (
            <article className="mini-card" key={run.id}>
              <strong>{run.kind}</strong>
              <span>{run.mode}</span>
              <p>{run.summary}</p>
              <ul>
                {run.steps.map((step) => (
                  <li key={`${run.id}-${step.agent}`}>{step.agent}: {step.detail}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>
    </AppShell>
  )
}
