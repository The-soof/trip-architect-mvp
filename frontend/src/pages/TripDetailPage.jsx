import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiRequest } from '../api/client'
import AppShell from '../components/AppShell'
import GlobeLoader from '../components/GlobeLoader'
import InventoryPanel from '../components/InventoryPanel'
import TravelJourneys from '../components/TravelJourneys'
import { BUILDING_LOADER, OPTIONS_LOADER } from '../lib/loaderCopy'
import OptionCard from '../components/OptionCard'
import Timeline from '../components/Timeline'
import { useSession } from '../hooks/useSession.jsx'
import { tripWindow } from '../lib/format'

const TRIP_TABS = ['Options', 'Itinerary', 'Stays', 'Travel']

function getBriefDetails(text) {
  if (!text) return { originalBrief: '', regenNotes: [] }
  const parts = text.split(/regeneration note:/i)
  const originalBrief = parts[0].split(/traveler profile interests:/i)[0].trim()
  const regenNotes = parts
    .slice(1)
    .map((p) => p.split(/traveler profile interests:/i)[0].trim())
    .filter(Boolean)
  return { originalBrief, regenNotes }
}

function getCityDisplay(city) {
  if (!city) return ''
  const trimmed = city.trim()
  if (trimmed.length === 3) return trimmed.toUpperCase()
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
}

function getReturnDisplay(city) {
  if (!city) return 'Flexible'
  const trimmed = city.trim()
  if (trimmed.toLowerCase() === 'none') return 'One-way'
  if (trimmed.length === 3) return trimmed.toUpperCase()
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
}

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
  const [briefExpanded, setBriefExpanded] = useState(false)

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
    return <GlobeLoader fullscreen messages={OPTIONS_LOADER.messages} showTips title={OPTIONS_LOADER.title} />
  }

  // Surface any "estimated data" notices recorded on the most recent itinerary run.
  const travelNotices = latestItineraryRun?.output_payload?.travel_notices || []

  const nextSteps = [
    { label: 'Route options generated', done: trip.options.length > 0 },
    { label: 'Lock in your route direction', done: Boolean(trip.selected_option_id) },
    { label: 'Itinerary generated', done: Boolean(itinerary) },
    {
      label: 'Select your travel journey',
      done: Boolean(trip.selected_journey_id),
    },
    {
      label: 'Choose your lodging stays',
      done: trip.confirmed_bookings.some((b) => b.booking_type === 'hotel' && b.selection_state === 'confirmed'),
    },
  ]

  const faqs = [
    { q: 'Are these live prices?', a: 'Flight pricing is modeled as an estimate, not a live fare hold.' },
    { q: 'How is lodging estimated?', a: "Lodging assumes each option's pacing across its stops." },
    {
      q: 'How are food and activities budgeted?',
      a: 'Food and activity budgets scale with the requested budget tier and traveler count.',
    },
    {
      q: 'Where do the booking links go?',
      a: 'Each travel step links out to a live search on a relevant provider—Kayak for flights, Ferryhopper for ferries, Omio for rail, and Booking.com for stays. Trip Architect does not add service fees.',
    },
  ]

  return (
    <AppShell
      compactHeader
      title={trip.destination_candidates.join(' · ')}
      subtitle={`${trip.origin} · ${tripWindow(trip.start_date, trip.end_date)} · ${trip.status}`}
      actions={
        <div className="trip-detail-actions">
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
          <p className="eyebrow">Route locked</p>
          <h2>A travel journey has been selected, so this route is now permanent.</h2>
          <p>You can still review the itinerary, stays, and your selected journey, but you can no longer regenerate options or switch to another route.</p>
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
          <div className="regenerate-actions">
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
        <div className="summary-brief-wrapper">
          <p className="eyebrow">Trip brief</p>
          <div className="summary-brief-body">
            <p className="summary-brief">
              {trip.brief_summary ? trip.brief_summary : (getBriefDetails(trip.trip_style).originalBrief.length > 120 ? getBriefDetails(trip.trip_style).originalBrief.slice(0, 117) + '...' : getBriefDetails(trip.trip_style).originalBrief)}
            </p>
            <button
              type="button"
              className="brief-toggle-btn"
              onClick={() => setBriefExpanded(!briefExpanded)}
            >
              {briefExpanded ? 'Show less' : 'View original input'}
            </button>
          </div>
          {briefExpanded && (
            <div className="summary-brief-expanded">
              <p className="brief-expanded-original">{getBriefDetails(trip.trip_style).originalBrief}</p>
              {getBriefDetails(trip.trip_style).regenNotes.length > 0 && (
                <div className="brief-expanded-adjustments">
                  <strong>Adjustments made during planning:</strong>
                  <ul>
                    {getBriefDetails(trip.trip_style).regenNotes.map((note, idx) => (
                      <li key={idx}>“{note}”</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="summary-metadata">
          <div className="summary-stat">
            <span>Origin</span>
            <strong>{getCityDisplay(trip.origin)}</strong>
          </div>
          <div className="summary-stat">
            <span>Return</span>
            <strong>{getReturnDisplay(selectedOption?.return_city || trip.options[0]?.return_city)}</strong>
          </div>
          <div className="summary-stat">
            <span>Travelers</span>
            <strong>{trip.traveler_count}</strong>
          </div>
          <div className="summary-stat">
            <span>Budget</span>
            <strong>{trip.budget_range || 'Flexible'}</strong>
          </div>
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
        <GlobeLoader
          messages={(BUILDING_LOADER[activeTab] || BUILDING_LOADER.Itinerary).messages}
          title={(BUILDING_LOADER[activeTab] || BUILDING_LOADER.Itinerary).title}
        />
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

          {trip.options.length ? (
            <details className="assumption-disclosure" aria-label="Estimate assumptions">
              <summary>Assumptions (3)</summary>
              <div className="assumption-list">
                <small>Flight pricing is modeled as an estimate, not a live fare hold.</small>
                <small>Lodging assumes each option&apos;s pacing across its stops.</small>
                <small>Food and activity budgets scale with the requested budget tier and traveler count.</small>
              </div>
            </details>
          ) : null}

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
          <TravelJourneys
            bookingSavingKey={bookingSavingKey}
            journeys={trip.travel_journeys}
            notices={travelNotices}
            onSelectJourney={handleBookingSelection}
            routeLocked={Boolean(trip.selected_journey_id)}
            selectedJourneyId={trip.selected_journey_id}
          />
        </section>
      ) : null}

      <section className="trip-footer-grid" aria-label="Trip progress and FAQ">
        <div className="surface-card next-steps-card">
          <p className="eyebrow">Next steps</p>
          <ul className="next-steps-list">
            {nextSteps.map((step) => (
              <li className={`next-step${step.done ? ' is-done' : ''}`} key={step.label}>
                <span aria-hidden="true" className="next-step-check" />
                <span>{step.label}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="surface-card faq-card">
          <p className="eyebrow">FAQ</p>
          <dl className="faq-list">
            {faqs.map((faq) => (
              <div className="faq-item" key={faq.q}>
                <dt>{faq.q}</dt>
                <dd>{faq.a}</dd>
              </div>
            ))}
          </dl>
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
