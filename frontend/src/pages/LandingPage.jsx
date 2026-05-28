import { Navigate } from 'react-router-dom'
import AuthPanel from '../components/AuthPanel'
import { useSession } from '../hooks/useSession.jsx'

export default function LandingPage() {
  const { token } = useSession()

  if (token) {
    return <Navigate replace to="/app" />
  }

  return (
    <main className="landing-shell">
      <section className="hero-panel">
        <div className="hero-copy">
          <p className="eyebrow">AI travel planner</p>
          <h1>From a vague summer idea to a saved bookable itinerary in minutes.</h1>
          <p className="hero-body">
            Trip Architect compares realistic destination combinations, explains the tradeoffs, expands a selected plan
            into a day-by-day itinerary, and hands off booking links without making the traveler juggle ten browser tabs.
          </p>
          <div className="hero-metrics">
            <article>
              <strong>3-5</strong>
              <span>structured route options</span>
            </article>
            <article>
              <strong>1</strong>
              <span>saved workspace for every trip</span>
            </article>
            <article>
              <strong>2</strong>
              <span>planning modes: mock now, deepagents-ready when keys exist</span>
            </article>
          </div>
        </div>

        <div className="hero-preview surface-card">
          <p className="eyebrow">What the MVP does</p>
          <h2>Compare, choose, deepen, save.</h2>
          <ul>
            <li>Origin, dates, destinations, budget, pace, and trip style intake</li>
            <li>AI-generated options with rationale, estimated cost bands, and route pacing</li>
            <li>Detailed itinerary timeline plus neighborhood guidance</li>
            <li>Flight and hotel discovery with direct outbound links</li>
            <li>Saved trips dashboard with agent run visibility</li>
          </ul>
        </div>
      </section>

      <AuthPanel />
    </main>
  )
}
