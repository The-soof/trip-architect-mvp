import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiRequest } from '../api/client'
import AppShell from '../components/AppShell'
import GlobeLoader from '../components/GlobeLoader'
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
  const [showRegenerateForm, setShowRegenerateForm] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [regenerateFeedback, setRegenerateFeedback] = useState('')
  const [pendingSelectionOptionId, setPendingSelectionOptionId] = useState('')

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
  const isTripLocked = Boolean(trip?.selected_option_id)
  const isFlightLocked = trip?.flight_selection_locked
  const isPending = isPlanningOptions || isBuildingItinerary
  const showPlanningScreen = isPlanningOptions && !trip?.options.length
  const requiresSelectedOption = activeTab !== 'Options'
  // Itinerary, stays, and travel are generated after an option is committed.
  const isGeneratingDetail = isBuildingItinerary || Boolean(selectingOptionId)

  useEffect(() => {
    if (!isPending) {
      return undefined
    }
    const intervalId = window.setInterval(() => {
      loadTrip({ silent: true })
    }, 2500)
    return () => window.clearInterval(intervalId)
  }, [isPending, tripId, token])

  function handleSelectIntent(optionId) {
    if (isTripLocked) {
      return
    }
    setPendingSelectionOptionId(optionId)
    setError('')
  }

  async function handleConfirmSelection() {
    if (!trip || !pendingSelectionOptionId) {
      return
    }
    setSelectingOptionId(pendingSelectionOptionId)
    try {
      const payload = await apiRequest(`/trips/${trip.id}/select-option/${pendingSelectionOptionId}`, {
        method: 'POST',
        token,
      })
      setTrip(payload)
      setActiveTab('Options')
      setPendingSelectionOptionId('')
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

  async function handleRegenerate() {
    setRegenerating(true)
    setError('')
    try {
      const payload = await apiRequest(`/trips/${trip.id}/regenerate`, {
        method: 'POST',
        token,
        body: { feedback: regenerateFeedback.trim() },
      })
      setTrip(payload)
      setShowRegenerateForm(false)
      setRegenerateFeedback('')
      setActiveTab('Options')
    } catch (regenError) {
      setError(regenError.message)
    } finally {
      setRegenerating(false)
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
    return <GlobeLoader fullscreen />
  }

  return (
    <AppShell
      title={trip.destination_candidates.join(' · ')}
      subtitle={`${trip.origin} · ${tripWindow(trip.start_date, trip.end_date)} · ${trip.status}`}
      actions={
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {!isPending && !isTripLocked && !isFlightLocked && (
            <button
              className="ghost-button"
              disabled={regenerating}
              id="regenerate-trip-btn"
              onClick={() => setShowRegenerateForm((prev) => !prev)}
              type="button"
            >
              {showRegenerateForm ? 'Cancel' : 'Adjust \u0026 Regenerate'}
            </button>
          )}
          <button className="primary-button" disabled={saving} onClick={handleSave} type="button">
            {trip.saved_trip ? 'Saved to dashboard' : saving ? 'Saving...' : 'Save trip'}
          </button>
        </div>
      }
    >
      {error ? <p className="inline-error">{error}</p> : null}

      {isTripLocked ? (
        <section className="surface-card planner-notice planner-lock-notice" aria-live="polite">
          <p className="eyebrow">Trip locked</p>
          <h2>This route is locked in and cannot be changed.</h2>
          <p>
            The selected option is now your committed trip direction. Other routes are disabled, regeneration is off,
            and itinerary, hotel, and flight discovery will continue building around this route only.
          </p>
        </section>
      ) : null}

      {isFlightLocked ? (
        <section className="surface-card planner-notice" aria-live="polite">
          <p className="eyebrow">Flight locked</p>
          <h2>A flight has been saved, so this route is now permanent.</h2>
          <p>You can still review the itinerary, stays, and the saved flight, but you can no longer regenerate options or switch to another route.</p>
        </section>
      ) : null}

      {showRegenerateForm ? (
        <section className="surface-card regenerate-form-card" aria-label="Adjust and regenerate">
          <p className="eyebrow">Adjust \u0026 Regenerate</p>
          <h2>Update your preferences and get fresh options.</h2>
          <p>Describe what you\'d like changed — fewer stops, more beach, lower budget, specific vibe, etc. Your feedback will be included in the next planning run.</p>
          <label htmlFor="regen-feedback-input">
            What should the planner change?
            <textarea
              id="regen-feedback-input"
              maxLength={600}
              onChange={(e) => setRegenerateFeedback(e.target.value)}
              placeholder="e.g. Fewer stops, more time in each city. Focus on beach destinations over nightlife."
              rows={3}
              value={regenerateFeedback}
            />
          </label>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              className="primary-button"
              disabled={regenerating}
              id="confirm-regenerate-btn"
              onClick={handleRegenerate}
              type="button"
            >
              {regenerating ? 'Regenerating...' : 'Regenerate options'}
            </button>
            <button
              className="ghost-button"
              onClick={() => { setShowRegenerateForm(false); setRegenerateFeedback('') }}
              type="button"
            >
              Cancel
            </button>
          </div>
        </section>
      ) : null}

      {trip.planning_mode === 'mock' ? (
        <section className="surface-card planner-notice planner-mock-notice" aria-label="Mock mode notice">
          <p className="eyebrow">Sandbox mode active</p>
          <h2>This trip was planned using the deterministic fallback planner, not the live Gemini pipeline.</h2>
          <p>
            Route options, cost estimates, and itinerary structure are generated by a deterministic local algorithm.
            Booking links are real and will open Kayak or Booking.com pre-filled with your dates,
            but prices and hotel names are placeholders. The live Gemini and research pipeline is enabled and will activate
            automatically on your next trip.
          </p>
        </section>
      ) : null}

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

      {isGeneratingDetail && activeTab !== 'Options' ? (
        <GlobeLoader />
      ) : (
        <>
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
                onSelect={handleSelectIntent}
                option={option}
                selectionDisabled={Boolean(isTripLocked && selectedOption?.id !== option.id)}
                selectionLabel="Trip locked"
                selectionLocked={Boolean(isTripLocked && selectedOption?.id === option.id)}
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
            flightSelectionLocked={trip.flight_selection_locked}
            flights={trip.flight_options}
            hotels={trip.hotel_options}
            lockedFlightOptionId={trip.locked_flight_option_id}
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
            flightSelectionLocked={trip.flight_selection_locked}
            flights={trip.flight_options}
            hotels={trip.hotel_options}
            lockedFlightOptionId={trip.locked_flight_option_id}
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
        </>
      )}

      {pendingSelectionOptionId ? (
        <div className="modal-backdrop" role="presentation">
          <section
            aria-describedby="trip-lock-modal-copy"
            aria-labelledby="trip-lock-modal-title"
            aria-modal="true"
            className="modal-card surface-card"
            role="dialog"
          >
            <p className="eyebrow">Confirm trip selection</p>
            <h2 id="trip-lock-modal-title">Once a trip is selected it cannot be changed</h2>
            <p id="trip-lock-modal-copy">
              Confirming this route will permanently lock the trip choice. After that, Trip Architect will build the
              itinerary, hotel recommendations, and flight options for this route only.
            </p>
            <div className="modal-actions">
              <button
                className="primary-button"
                disabled={Boolean(selectingOptionId)}
                onClick={handleConfirmSelection}
                type="button"
              >
                {selectingOptionId ? 'Confirming...' : 'Confirm'}
              </button>
              <button
                className="ghost-button"
                disabled={Boolean(selectingOptionId)}
                onClick={() => setPendingSelectionOptionId('')}
                type="button"
              >
                Cancel
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </AppShell>
  )
}
