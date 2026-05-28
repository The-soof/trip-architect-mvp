import { useEffect, useState } from 'react'
import AppShell from '../components/AppShell'
import { apiRequest } from '../api/client'
import { useSession } from '../hooks/useSession.jsx'

function interestsToString(interests) {
  return (interests || []).join(', ')
}

export default function ProfilePage({ loadingWorkspace, profile, reloadProfile }) {
  const { token } = useSession()
  const [form, setForm] = useState({
    home_airport: '',
    budget_preference: 'Mid-range',
    pace_preference: 'Balanced',
    interests: '',
  })
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!profile) {
      return
    }
    setForm({
      home_airport: profile.home_airport || '',
      budget_preference: profile.budget_preference || 'Mid-range',
      pace_preference: profile.pace_preference || 'Balanced',
      interests: interestsToString(profile.interests),
    })
  }, [profile])

  async function handleSubmit(event) {
    event.preventDefault()
    setSaving(true)
    setMessage('')
    setError('')
    try {
      await apiRequest('/profile/me', {
        method: 'PUT',
        token,
        body: {
          home_airport: form.home_airport || null,
          budget_preference: form.budget_preference || null,
          pace_preference: form.pace_preference || null,
          interests: form.interests
            .split(',')
            .map((value) => value.trim())
            .filter(Boolean),
        },
      })
      await reloadProfile()
      setMessage('Preferences saved. Future plans will use these defaults when helpful.')
    } catch (saveError) {
      setError(saveError.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <AppShell
      title="Traveler profile and planning preferences"
      subtitle="Set defaults once so new trips inherit your pacing, budget, and interest signals."
    >
      {loadingWorkspace ? (
        <section className="surface-card planner-notice" aria-live="polite">
          <p className="eyebrow">Syncing profile</p>
          <h2>Loading the latest traveler defaults.</h2>
          <p>Your saved preferences will appear here as soon as they finish loading.</p>
        </section>
      ) : null}

      <form className="planner-form surface-card" onSubmit={handleSubmit}>
        <div className="form-grid">
          <label>
            Home airport
            <input
              disabled={loadingWorkspace}
              onChange={(event) => setForm((current) => ({ ...current, home_airport: event.target.value }))}
              placeholder="JFK"
              value={form.home_airport}
            />
          </label>

          <label>
            Default budget
            <select
              disabled={loadingWorkspace}
              onChange={(event) => setForm((current) => ({ ...current, budget_preference: event.target.value }))}
              value={form.budget_preference}
            >
              <option>Budget</option>
              <option>Mid-range</option>
              <option>Luxury</option>
            </select>
          </label>

          <label>
            Preferred pace
            <select
              disabled={loadingWorkspace}
              onChange={(event) => setForm((current) => ({ ...current, pace_preference: event.target.value }))}
              value={form.pace_preference}
            >
              <option>Slow</option>
              <option>Balanced</option>
              <option>Fast-paced</option>
            </select>
          </label>

          <label>
            Interests
            <input
              disabled={loadingWorkspace}
              onChange={(event) => setForm((current) => ({ ...current, interests: event.target.value }))}
              placeholder="food, nightlife, water, architecture"
              value={form.interests}
            />
          </label>
        </div>

        <div className="surface-subtle">
          <strong>How this is used</strong>
          <p>
            The planner will use these defaults to enrich route ranking, pacing, and itinerary assembly when a trip brief
            is vague or incomplete.
          </p>
        </div>

        {message ? <p className="inline-success">{message}</p> : null}
        {error ? <p className="inline-error">{error}</p> : null}

        <button className="primary-button" disabled={loadingWorkspace || saving} type="submit">
          {saving ? 'Saving...' : 'Save preferences'}
        </button>
      </form>
    </AppShell>
  )
}
