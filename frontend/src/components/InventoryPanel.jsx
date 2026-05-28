import { useMemo, useState } from 'react'
import { formatMoney } from '../lib/format'

export default function InventoryPanel({ flights, hotels, confirmedBookings, onUpdateBookingSelection, bookingSavingKey }) {
  const [flightSort, setFlightSort] = useState('price')
  const [hotelSort, setHotelSort] = useState('rating')
  const [selectionFilter, setSelectionFilter] = useState('all')

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
      if (selectionFilter === 'all') {
        return true
      }
      return bookingMap[`flight:${flight.id}`] === selectionFilter
    })
  }, [bookingMap, flightSort, flights, selectionFilter])

  const visibleHotels = useMemo(() => {
    const next = [...hotels]
    if (hotelSort === 'price') {
      next.sort((a, b) => a.nightly_rate - b.nightly_rate)
    } else {
      next.sort((a, b) => b.rating - a.rating)
    }
    return next.filter((hotel) => {
      if (selectionFilter === 'all') {
        return true
      }
      return bookingMap[`hotel:${hotel.id}`] === selectionFilter
    })
  }, [bookingMap, hotelSort, hotels, selectionFilter])

  return (
    <section className="inventory-grid">
      <div className="surface-card">
        <div className="section-header">
          <div>
            <p className="eyebrow">Flights</p>
            <h2>Booking discovery</h2>
          </div>
          <p>These are link-out options aligned to the selected route and pacing.</p>
        </div>
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
            <select onChange={(event) => setSelectionFilter(event.target.value)} value={selectionFilter}>
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
              return (
                <article className="inventory-card inventory-block" key={flight.id}>
                  <div>
                    <strong>{flight.carrier}</strong>
                    <p>{flight.route_summary}</p>
                    <small className="muted-inline">
                      {flight.source_name} · {flight.match_reason}
                    </small>
                  </div>
                  <div className="inventory-meta">
                    <span>{formatMoney(flight.price)}</span>
                    <small>{flight.comfort_label}</small>
                    <small className={`selection-pill selection-${selectionState}`}>{selectionState}</small>
                  </div>
                  <div className="trip-card-actions">
                    <button
                      className="ghost-button"
                      disabled={bookingSavingKey === `flight:${flight.id}`}
                      onClick={() => onUpdateBookingSelection('flight', flight.id, 'saved')}
                      type="button"
                    >
                      Save
                    </button>
                    <button
                      className="secondary-button"
                      disabled={bookingSavingKey === `flight:${flight.id}`}
                      onClick={() => onUpdateBookingSelection('flight', flight.id, 'confirmed')}
                      type="button"
                    >
                      Confirm
                    </button>
                    <button
                      className="ghost-button"
                      disabled={bookingSavingKey === `flight:${flight.id}`}
                      onClick={() => onUpdateBookingSelection('flight', flight.id, 'none')}
                      type="button"
                    >
                      Clear
                    </button>
                    <a href={flight.booking_url} rel="noreferrer" target="_blank">
                      Open booking
                    </a>
                  </div>
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

      <div className="surface-card">
        <div className="section-header">
          <div>
            <p className="eyebrow">Hotels</p>
            <h2>Stay recommendations</h2>
          </div>
          <p>Neighborhood-first options that match the itinerary rhythm.</p>
        </div>
        <div className="toolbar-row">
          <label>
            Sort hotels
            <select onChange={(event) => setHotelSort(event.target.value)} value={hotelSort}>
              <option value="rating">Highest rating</option>
              <option value="price">Lowest nightly rate</option>
            </select>
          </label>
        </div>
        <div className="inventory-list">
          {visibleHotels.length ? (
            visibleHotels.map((hotel) => {
              const selectionState = bookingMap[`hotel:${hotel.id}`] || 'available'
              return (
                <article className="inventory-card inventory-block" key={hotel.id}>
                  <div>
                    <strong>{hotel.name}</strong>
                    <p>
                      {hotel.city} · {hotel.neighborhood}
                    </p>
                    <small className="muted-inline">
                      {hotel.source_name} · {hotel.match_reason}
                    </small>
                  </div>
                  <div className="inventory-meta">
                    <span>{formatMoney(hotel.nightly_rate)}/night</span>
                    <small>
                      {hotel.style_label} · {hotel.rating.toFixed(1)}
                    </small>
                    <small className={`selection-pill selection-${selectionState}`}>{selectionState}</small>
                  </div>
                  <div className="trip-card-actions">
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
                    <a href={hotel.booking_url} rel="noreferrer" target="_blank">
                      Open booking
                    </a>
                  </div>
                </article>
              )
            })
          ) : (
            <article className="empty-state-card">
              <strong>No hotels match the current sort or selection state.</strong>
              <p>Reset the filter to browse the full list again.</p>
            </article>
          )}
        </div>
      </div>
    </section>
  )
}
