import { useMemo, useState } from 'react'
import { formatMoney } from '../lib/format'

export default function InventoryPanel({
  flights,
  hotels,
  confirmedBookings,
  onUpdateBookingSelection,
  bookingSavingKey,
  flightSelectionLocked = false,
  lockedFlightOptionId = null,
  mode = 'all',
}) {
  const [flightSort, setFlightSort] = useState('price')
  const [hotelSort, setHotelSort] = useState('rating')
  const [flightSelectionFilter, setFlightSelectionFilter] = useState('all')
  const [hotelSelectionFilter, setHotelSelectionFilter] = useState('all')
  const showFlights = mode === 'all' || mode === 'flights'
  const showHotels = mode === 'all' || mode === 'hotels'

  const bookingMap = useMemo(
    () =>
      Object.fromEntries(
        confirmedBookings.map((booking) => [`${booking.booking_type}:${booking.source_option_id}`, booking.selection_state]),
      ),
    [confirmedBookings],
  )

  const visibleFlights = useMemo(() => {
    const next = [...flights]
    if (flightSort === 'comfort') {
      next.sort((a, b) => a.stops - b.stops || a.price - b.price)
    } else {
      next.sort((a, b) => a.price - b.price)
    }
    return next.filter((flight) => {
      if (flightSelectionFilter === 'all') {
        return true
      }
      return bookingMap[`flight:${flight.id}`] === flightSelectionFilter
    })
  }, [bookingMap, flightSort, flights, flightSelectionFilter])

  const visibleHotels = useMemo(() => {
    const next = [...hotels]
    if (hotelSort === 'price') {
      next.sort((a, b) => a.nightly_rate - b.nightly_rate)
    } else {
      next.sort((a, b) => b.rating - a.rating)
    }
    return next.filter((hotel) => {
      if (hotelSelectionFilter === 'all') {
        return true
      }
      return bookingMap[`hotel:${hotel.id}`] === hotelSelectionFilter
    })
  }, [bookingMap, hotelSort, hotels, hotelSelectionFilter])

  return (
    <section className={`inventory-grid${mode === 'all' ? '' : ' inventory-grid--single'}`}>
      {showFlights ? (
        <div className="surface-card">
          <div className="section-header">
            <div>
              <p className="eyebrow">Flights</p>
              <h2>Booking discovery</h2>
            </div>
            <p>These are link-out options aligned to the selected route and pacing.</p>
          </div>
          {flightSelectionLocked ? (
            <p className="inline-error">
              A flight has already been saved for this trip. The selected route is now locked and other flight options are read-only.
            </p>
          ) : null}
          <div className="toolbar-row">
            <label>
              Sort flights
              <select onChange={(event) => setFlightSort(event.target.value)} value={flightSort}>
                <option value="price">Lowest price</option>
                <option value="comfort">Fewest stops</option>
              </select>
            </label>
            <label>
              Selection filter
              <select onChange={(event) => setFlightSelectionFilter(event.target.value)} value={flightSelectionFilter}>
                <option value="all">Show all</option>
                <option value="saved">Saved</option>
                <option value="confirmed">Confirmed</option>
              </select>
            </label>
          </div>
          <div className="inventory-list">
            {visibleFlights.length ? (
              visibleFlights.map((flight) => {
                const selectionState = bookingMap[`flight:${flight.id}`] || 'available'
                const isLockedFlight = flightSelectionLocked && lockedFlightOptionId === flight.id
                const restrictFlightActions = flightSelectionLocked && lockedFlightOptionId !== flight.id
                return (
                  <article className="inventory-card" key={flight.id}>
                    <div className="inventory-card-head">
                      <div className="inventory-card-title">
                        <strong>{flight.carrier}</strong>
                        <p>{flight.route_summary}</p>
                      </div>
                      <div className="inventory-card-price">
                        <strong>{formatMoney(flight.price)}</strong>
                        <small>{flight.comfort_label}</small>
                      </div>
                    </div>
                    <p className="inventory-card-meta">
                      {flight.source_name} · {flight.match_reason}
                    </p>
                    <div className="inventory-card-foot">
                      <span className={`status-pill status-${selectionState}`}>{selectionState}</span>
                      <div className="inventory-actions">
                        <button
                          className="ghost-button"
                          disabled={bookingSavingKey === `flight:${flight.id}` || flightSelectionLocked}
                          onClick={() => onUpdateBookingSelection('flight', flight.id, 'saved')}
                          type="button"
                        >
                          Save
                        </button>
                        <button
                          className="secondary-button"
                          disabled={bookingSavingKey === `flight:${flight.id}` || restrictFlightActions}
                          onClick={() => onUpdateBookingSelection('flight', flight.id, 'confirmed')}
                          type="button"
                        >
                          Confirm
                        </button>
                        <button
                          className="ghost-button"
                          disabled={bookingSavingKey === `flight:${flight.id}` || flightSelectionLocked}
                          onClick={() => onUpdateBookingSelection('flight', flight.id, 'none')}
                          type="button"
                        >
                          Clear
                        </button>
                        <a className="ghost-button" href={flight.booking_url} rel="noreferrer" target="_blank">
                          Open booking ↗
                        </a>
                      </div>
                    </div>
                    {isLockedFlight ? (
                      <small className="muted-inline inventory-locked-note">Locked flight selection</small>
                    ) : null}
                  </article>
                )
              })
            ) : (
              <article className="empty-state-card">
                <strong>No flight options match the current filter.</strong>
                <p>Try a different sort or show all selections to bring more routes back into view.</p>
              </article>
            )}
          </div>
        </div>
      ) : null}

      {showHotels ? (
        <div className="surface-card">
          <div className="section-header">
            <div>
              <p className="eyebrow">Stays</p>
              <h2>Stay recommendations</h2>
            </div>
            <p>Neighborhood-first options that match the itinerary rhythm.</p>
          </div>
          <div className="toolbar-row">
            <label>
              Sort stays
              <select onChange={(event) => setHotelSort(event.target.value)} value={hotelSort}>
                <option value="rating">Highest rating</option>
                <option value="price">Lowest nightly rate</option>
              </select>
            </label>
            <label>
              Selection filter
              <select onChange={(event) => setHotelSelectionFilter(event.target.value)} value={hotelSelectionFilter}>
                <option value="all">Show all</option>
                <option value="saved">Saved</option>
                <option value="confirmed">Confirmed</option>
              </select>
            </label>
          </div>
          <div className="inventory-list">
            {visibleHotels.length ? (
              visibleHotels.map((hotel) => {
                const selectionState = bookingMap[`hotel:${hotel.id}`] || 'available'
                return (
                  <article className="inventory-card" key={hotel.id}>
                    <div className="inventory-card-head">
                      <div className="inventory-card-title">
                        <strong>{hotel.name}</strong>
                        <p>
                          {hotel.city} · {hotel.neighborhood}
                        </p>
                      </div>
                      <div className="inventory-card-price">
                        <strong>{formatMoney(hotel.nightly_rate)}/night</strong>
                        <small>
                          {hotel.style_label} · {hotel.rating.toFixed(1)}
                        </small>
                      </div>
                    </div>
                    <p className="inventory-card-meta">
                      {hotel.source_name} · {hotel.match_reason}
                    </p>
                    <div className="inventory-card-foot">
                      <span className={`status-pill status-${selectionState}`}>{selectionState}</span>
                      <div className="inventory-actions">
                        <button
                          className="ghost-button"
                          disabled={bookingSavingKey === `hotel:${hotel.id}`}
                          onClick={() => onUpdateBookingSelection('hotel', hotel.id, 'saved')}
                          type="button"
                        >
                          Save
                        </button>
                        <button
                          className="secondary-button"
                          disabled={bookingSavingKey === `hotel:${hotel.id}`}
                          onClick={() => onUpdateBookingSelection('hotel', hotel.id, 'confirmed')}
                          type="button"
                        >
                          Confirm
                        </button>
                        <button
                          className="ghost-button"
                          disabled={bookingSavingKey === `hotel:${hotel.id}`}
                          onClick={() => onUpdateBookingSelection('hotel', hotel.id, 'none')}
                          type="button"
                        >
                          Clear
                        </button>
                        <a className="ghost-button" href={hotel.booking_url} rel="noreferrer" target="_blank">
                          Open booking ↗
                        </a>
                      </div>
                    </div>
                  </article>
                )
              })
            ) : (
              <article className="empty-state-card">
                <strong>No stays match the current sort or selection state.</strong>
                <p>Reset the filter to browse the full list again.</p>
              </article>
            )}
          </div>
        </div>
      ) : null}
    </section>
  )
}
