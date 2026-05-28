import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiRequest } from '../api/client'
import AppShell from '../components/AppShell'
import InventoryPanel from '../components/InventoryPanel'
import OptionCard from '../components/OptionCard'
import Timeline from '../components/Timeline'
import { useSession } from '../hooks/useSession.jsx'
import { tripWindow } from '../lib/format'

export default function TripDetailPage() {
  const { tripId } = useParams()
  const { token } = useSession()
  const [trip, setTrip] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [selectingOptionId, setSelectingOptionId] = useState('')
  const [bookingSavingKey, setBookingSavingKey] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadTrip() {
      try {
        const payload = await apiRequest(`/trips/${tripId}`, { token })
        setTrip(payload)
      } catch (loadError) {
        setError(loadError.message)
      } finally {
        setLoading(false)
      }
    }
    loadTrip()
  }, [token, tripId])

  const selectedOption = useMemo(
    () => trip?.options.find((option) => option.id === trip.selected_option_id) || null,
    [trip],
  )
  const itinerary = trip?.itineraries[0] || null

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

      <section className="options-grid">
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

      <Timeline itinerary={itinerary} />

      {trip.flight_options.length || trip.hotel_options.length ? (
        <InventoryPanel
          bookingSavingKey={bookingSavingKey}
          confirmedBookings={trip.confirmed_bookings}
          flights={trip.flight_options}
          hotels={trip.hotel_options}
          onUpdateBookingSelection={handleBookingSelection}
        />
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
