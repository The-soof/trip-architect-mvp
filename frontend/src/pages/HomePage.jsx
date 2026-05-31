import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import ReactiveBackground from '../components/ReactiveBackground'
import { useSession } from '../hooks/useSession.jsx'

// Compass / architect's-rose mark. Echoes the spoked brandmark dot used across
// the app, scaled up and tinted with the reactive background palette so the
// logo and the canvas behind it feel like one system. The logo is not final —
// this is a refined take on the existing mark.
function CompassLogo() {
  return (
    <svg className="home-logo" viewBox="0 0 120 120" role="img" aria-label="Trip Architect logo">
      <defs>
        <linearGradient id="home-logo-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#6bb8f5" />
          <stop offset="50%" stopColor="#abb1e2" />
          <stop offset="100%" stopColor="#f6c79c" />
        </linearGradient>
      </defs>
      <circle cx="60" cy="60" r="54" fill="none" stroke="url(#home-logo-grad)" strokeWidth="2.5" opacity="0.7" />
      <circle cx="60" cy="60" r="44" fill="none" stroke="#071226" strokeWidth="1" opacity="0.12" />
      {/* four-point compass star */}
      <path
        d="M60 14 L68 52 L106 60 L68 68 L60 106 L52 68 L14 60 L52 52 Z"
        fill="url(#home-logo-grad)"
        opacity="0.92"
      />
      {/* secondary diagonal points */}
      <path
        d="M60 30 L64 56 L90 60 L64 64 L60 90 L56 64 L30 60 L56 56 Z"
        fill="#071226"
        opacity="0.82"
      />
      <circle cx="60" cy="60" r="6" fill="#ffffff" />
      <circle cx="60" cy="60" r="3" fill="#071226" />
    </svg>
  )
}

const capabilities = [
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
  {
    step: '01',
    title: 'Describe the trip',
    body: 'Share origin, dates, traveler count, candidate destinations, and the pace you want.',
  },
  {
    step: '02',
    title: 'Compare ranked routes',
    body: 'Review 3–5 structured route options with budget ranges, fit scores, and honest tradeoffs.',
  },
  {
    step: '03',
    title: 'Deepen and save',
    body: 'Expand the winning plan into a day-by-day itinerary and keep every decision in one workspace.',
  },
]

export default function HomePage() {
  const { token, user } = useSession()
  const signedIn = Boolean(token)

  // Suppress the global page-background overlay so the reactive canvas reads as
  // the sole backdrop while the home page is mounted.
  useEffect(() => {
    document.body.classList.add('home-active')
    return () => document.body.classList.remove('home-active')
  }, [])

  return (
    <div className="home-page">
      <ReactiveBackground />

      <header className="home-nav">
        <Link className="brandmark home-brandmark" to="/">
          <span className="brandmark-dot" />
          <span>
            Trip Architect
            <small>Travel planning workspace</small>
          </span>
        </Link>
        <nav className="home-nav-actions">
          {signedIn ? (
            <Link className="home-account" to="/app">
              <span className="home-account-name">{user?.full_name || 'Traveler'}</span>
              {user?.email ? <span className="home-account-email">{user.email}</span> : null}
            </Link>
          ) : (
            <Link className="ghost-button" to="/sign-in">
              Sign in
            </Link>
          )}
          <Link className="primary-button" to="/app">
            Get started
          </Link>
        </nav>
      </header>

      <section className="home-hero" aria-label="Trip Architect">
        <CompassLogo />
        <h1 className="home-wordmark">Trip Architect</h1>
        <p className="home-tagline">Design the trip before you book it.</p>
        <a className="home-scroll-cue" href="#learn-more" aria-label="Scroll to learn more">
          <span>Scroll to explore</span>
          <span className="home-scroll-arrow" aria-hidden="true">
            ↓
          </span>
        </a>
      </section>

      <main className="home-content" id="learn-more">
        <section className="home-section home-intro surface-card">
          <p className="eyebrow">What it does</p>
          <h2>From a vague summer idea to a saved, bookable itinerary in minutes.</h2>
          <p>
            Trip Architect compares realistic destination combinations, explains the tradeoffs, expands a selected
            plan into a day-by-day itinerary, and keeps the planning decisions together in one organized workspace.
            It is useful before flights are booked, useful after the route is chosen, and still useful when it is time
            to save the details.
          </p>
        </section>

        <section className="home-section" aria-label="How it works">
          <div className="home-section-head">
            <p className="eyebrow">How it works</p>
            <h2>Compare, choose, deepen, save.</h2>
          </div>
          <ol className="home-steps">
            {workflow.map((item) => (
              <li className="surface-card home-step" key={item.step}>
                <span className="home-step-index">{item.step}</span>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="home-section" aria-label="Why it helps">
          <div className="home-section-head">
            <p className="eyebrow">Why it helps</p>
            <h2>Structure for the messy middle of planning.</h2>
          </div>
          <div className="home-capabilities">
            {capabilities.map((cap) => (
              <article className="surface-card home-capability" key={cap.title}>
                <h3>{cap.title}</h3>
                <p>{cap.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="home-section home-cta surface-card">
          <p className="eyebrow">Ready when you are</p>
          <h2>Plan your next trip with a clear head.</h2>
          <p>Open the workspace and turn your next idea into a structured, bookable plan.</p>
          {signedIn ? null : (
            <div className="home-hero-actions">
              <Link className="primary-button home-hero-cta" to="/app">
                Get started
              </Link>
              <Link className="ghost-button home-hero-cta" to="/sign-in">
                Sign in
              </Link>
            </div>
          )}
        </section>

        <footer className="home-footer">
          <p>Structured planning, itinerary depth, and booking discovery in one workspace.</p>
          <div className="footer-links">
            <Link to="/privacy">Privacy</Link>
            <Link to="/terms">Terms</Link>
            <a href="mailto:support@triparchitect.app">Support</a>
          </div>
        </footer>
      </main>
    </div>
  )
}
