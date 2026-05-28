import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import App from './App'

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

test('renders landing page hero for signed out users', () => {
  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <App />
    </MemoryRouter>,
  )

  expect(screen.getByText(/saved bookable itinerary/i)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /start planning/i })).toBeInTheDocument()
})

test('auth panel switches to sign in mode', async () => {
  const user = (await import('@testing-library/user-event')).default.setup()

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <App />
    </MemoryRouter>,
  )

  await user.click(screen.getByRole('button', { name: /sign in/i }))

  expect(screen.getByRole('button', { name: /continue planning/i })).toBeInTheDocument()
})

test('sign-in route opens the auth panel in login mode', () => {
  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }} initialEntries={['/sign-in']}>
      <App />
    </MemoryRouter>,
  )

  expect(screen.getByRole('button', { name: /continue planning/i })).toBeInTheDocument()
  expect(screen.queryByLabelText(/full name/i)).not.toBeInTheDocument()
})

test('trip detail shows background planning state while options are still generating', async () => {
  window.localStorage.setItem(
    'trip-architect-session',
    JSON.stringify({
      token: 'test-token',
      user: { id: 'user-1', email: 'alex@example.com', full_name: 'Alex Rivera' },
    }),
  )

  const pendingTrip = {
    id: 'trip-1',
    origin: 'New York',
    start_date: '2026-08-10',
    end_date: '2026-08-20',
    destination_candidates: ['Barcelona', 'Split'],
    trip_style: 'Fun summer trip with food and water.',
    budget_range: 'Mid-range',
    traveler_count: 2,
    pace_preference: 'Balanced',
    planning_mode: 'mock',
    status: 'planning',
    selected_option_id: null,
    created_at: '2026-05-28T07:00:00Z',
    updated_at: '2026-05-28T07:00:00Z',
    options: [],
    itineraries: [],
    flight_options: [],
    hotel_options: [],
    confirmed_bookings: [],
    agent_runs: [
      {
        id: 'run-1',
        kind: 'options',
        mode: 'pending',
        status: 'running',
        summary: 'Planning trip options in the background.',
        input_payload: {},
        output_payload: { options_count: 0 },
        steps: [],
        sources: [],
        created_at: '2026-05-28T07:00:00Z',
        updated_at: '2026-05-28T07:00:00Z',
      },
    ],
    saved_trip: null,
  }

  vi.spyOn(global, 'fetch').mockImplementation((input) => {
    const url = String(input)
    let payload = null
    if (url.endsWith('/api/trips/trip-1')) {
      payload = pendingTrip
    } else if (url.endsWith('/api/trips')) {
      payload = { recent_trips: [], saved_trips: [] }
    } else if (url.endsWith('/api/profile/me')) {
      payload = {
        id: 'profile-1',
        home_airport: 'JFK',
        budget_preference: 'Mid-range',
        pace_preference: 'Balanced',
        interests: ['Food'],
      }
    } else {
      return Promise.reject(new Error(`Unexpected request: ${url}`))
    }

    return Promise.resolve(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }} initialEntries={['/trips/trip-1']}>
      <App />
    </MemoryRouter>,
  )

  expect(await screen.findByText(/Please wait, suggestions are being generated/i)).toBeInTheDocument()
  expect(screen.getByText(/This page refreshes automatically while the options run finishes/i)).toBeInTheDocument()
})

test('trip detail blocks itinerary tabs until a route option is selected', async () => {
  window.localStorage.setItem(
    'trip-architect-session',
    JSON.stringify({
      token: 'test-token',
      user: { id: 'user-1', email: 'alex@example.com', full_name: 'Alex Rivera' },
    }),
  )

  const user = (await import('@testing-library/user-event')).default.setup()

  const trip = {
    id: 'trip-2',
    origin: 'New York',
    start_date: '2026-08-10',
    end_date: '2026-08-20',
    destination_candidates: ['Barcelona', 'Split'],
    trip_style: 'Fun summer trip with food and water.',
    budget_range: 'Mid-range',
    traveler_count: 2,
    pace_preference: 'Balanced',
    planning_mode: 'deepagents',
    status: 'selected',
    selected_option_id: null,
    created_at: '2026-05-28T07:00:00Z',
    updated_at: '2026-05-28T07:00:00Z',
    options: [
      {
        id: 'opt-1',
        name: 'Barcelona first',
        summary: 'Good weather and beach balance.',
        rationale: 'Front-loads the city days and leaves beach recovery for later.',
        fit_score: 8.8,
        days_by_stop: [
          { city: 'Barcelona', nights: 5 },
          { city: 'Split', nights: 4 },
        ],
        estimated_total_min: 3200,
        estimated_total_max: 4100,
        pace_label: 'Balanced',
        cost_breakdown: {
          flights: { min: 1200, max: 1500 },
          lodging: { min: 1300, max: 1800 },
          local_transport: { min: 200, max: 280 },
          food_and_activities: { min: 500, max: 700 },
        },
        tradeoffs: ['Adds a mid-trip transfer day.'],
        warning_flags: [],
        price_assumptions: ['Assumes shoulder-season airfare from JFK.'],
      },
    ],
    itineraries: [],
    flight_options: [],
    hotel_options: [],
    confirmed_bookings: [],
    agent_runs: [],
    saved_trip: null,
  }

  vi.spyOn(global, 'fetch').mockImplementation((input) => {
    const url = String(input)
    let payload = null
    if (url.endsWith('/api/trips/trip-2')) {
      payload = trip
    } else if (url.endsWith('/api/trips')) {
      payload = { recent_trips: [], saved_trips: [] }
    } else if (url.endsWith('/api/profile/me')) {
      payload = {
        id: 'profile-1',
        home_airport: 'JFK',
        budget_preference: 'Mid-range',
        pace_preference: 'Balanced',
        interests: ['Food'],
      }
    } else {
      return Promise.reject(new Error(`Unexpected request: ${url}`))
    }

    return Promise.resolve(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })

  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }} initialEntries={['/trips/trip-2']}>
      <App />
    </MemoryRouter>,
  )

  await screen.findByRole('tab', { name: /Itinerary/i })
  await user.click(screen.getByRole('tab', { name: /Itinerary/i }))

  expect(screen.getByText(/Please select a trip option before continuing/i)).toBeInTheDocument()
  expect(screen.getByText(/Open the Options tab, pick the route you want/i)).toBeInTheDocument()
})
