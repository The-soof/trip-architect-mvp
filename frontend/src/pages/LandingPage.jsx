import { Link, Navigate } from 'react-router-dom'
import AuthPanel from '../components/AuthPanel'
import { useSession } from '../hooks/useSession.jsx'

const valueProps = [
  {
    title: 'Shortlist routes quickly',
    body: 'Compare realistic destination combinations with costs, pacing, and tradeoffs already organized.',
  },
  {
    title: 'Turn a route into a real trip',
    body: 'Expand the winning option into a day-by-day plan with neighborhood guidance and booking discovery.',
  },
  {
    title: 'Keep planning context together',
    body: 'Save trips, revisit previous requests, and reuse the best ones as the next starting point.',
  },
]

const workflow = [
  'Share origin, dates, traveler count, destinations, and pace.',
  'Review ranked route options with budget ranges and fit scores.',
  'Save the best plan and continue refining details in the workspace.',
]

export default function LandingPage({ initialMode = 'register' }) {
  const { token } = useSession()

  if (token) {
    return <Navigate replace to="/app" />
  }

  return (
    <main className="landing-shell">
      <header className="landing-header">
        <Link className="brandmark" to="/">
          <span className="brandmark-dot" />
          <span>
            Trip Architect
            <small>Travel planning workspace</small>
          </span>
        </Link>
        <div className="landing-header-note">
          <p>For travelers who want structure before they start booking.</p>
        </div>
      </header>

      <section className="hero-panel">
        <div className="hero-copy">
          <p className="eyebrow">AI travel planner</p>
          <h1>From a vague summer idea to a saved bookable itinerary in minutes.</h1>
          <p className="hero-body">
            Trip Architect compares realistic destination combinations, explains the tradeoffs, expands a selected plan
            into a day-by-day itinerary, and keeps the planning decisions in one organized workspace.
          </p>
          <div className="hero-proof">
            <strong>Built for the messy middle of planning.</strong>
            <p>Useful before flights are booked, useful after the route is chosen, and still useful when it is time to save the details.</p>
          </div>
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
              <span>planning modes ready for mock research or deeper agent-backed runs</span>
            </article>
          </div>
        </div>

        <div className="hero-stack">
          <div className="hero-preview surface-card">
            <p className="eyebrow">How it works</p>
            <h2>Compare, choose, deepen, save.</h2>
            <ol className="workflow-list">
              {workflow.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ol>
          </div>

          <AuthPanel initialMode={initialMode} />
        </div>
      </section>

      <section className="value-grid" aria-label="Product highlights">
        {valueProps.map((prop) => (
          <article className="surface-card value-card" key={prop.title}>
            <p className="eyebrow">Why it helps</p>
            <h2>{prop.title}</h2>
            <p>{prop.body}</p>
          </article>
        ))}
      </section>
    </main>
  )
}
