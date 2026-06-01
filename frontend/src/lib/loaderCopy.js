// Copy shown above the Globe loading screen during generation waits.
// The wording is intentionally phrased as ongoing activity rather than discrete
// "completed" steps, because the backend exposes no real progress signal — the
// rotation is purely time-based.

export const OPTIONS_LOADER = {
  title: 'Designing your trip',
  messages: [
    'Comparing routes and rough budgets…',
    'Weighing stops, pacing, and travel time…',
    'Balancing cost against time on the ground…',
    'Ranking the best-fit options for your brief…',
  ],
}

export const BUILDING_LOADER = {
  Itinerary: {
    title: 'Building your itinerary',
    messages: [
      'Mapping out your days, morning to evening…',
      'Balancing pace and travel time…',
      'Adding neighborhood and timing guidance…',
    ],
  },
  Stays: {
    title: 'Finding places to stay',
    messages: [
      'Scanning neighborhoods that fit your route…',
      'Matching stays to your budget and pace…',
      'Lining up booking options…',
    ],
  },
  Travel: {
    title: 'Searching travel options',
    messages: [
      'Looking at routes and flight times…',
      'Comparing options against your dates…',
      'Lining up booking links…',
    ],
  },
}
