import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import App from './App'

beforeEach(() => {
  window.localStorage.clear()
})

test('renders landing page hero for signed out users', () => {
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  )

  expect(screen.getByText(/saved bookable itinerary/i)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /start planning/i })).toBeInTheDocument()
})

test('auth panel switches to sign in mode', async () => {
  const user = (await import('@testing-library/user-event')).default.setup()

  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  )

  await user.click(screen.getByRole('button', { name: /sign in/i }))

  expect(screen.getByRole('button', { name: /continue planning/i })).toBeInTheDocument()
})
