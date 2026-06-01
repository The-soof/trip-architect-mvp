import { useEffect } from 'react'
import { Link, Navigate } from 'react-router-dom'
import AuthPanel from '../components/AuthPanel'
import { useSession } from '../hooks/useSession.jsx'

// Compact compass mark, shared visual language with the home page brandmark.
function CompassMark() {
  return (
    <svg className="auth-brand-logo" viewBox="0 0 120 120" role="img" aria-label="Trip Architect">
      <defs>
        <linearGradient id="auth-logo-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#6bb8f5" />
          <stop offset="50%" stopColor="#abb1e2" />
          <stop offset="100%" stopColor="#f6c79c" />
        </linearGradient>
      </defs>
      <circle cx="60" cy="60" r="54" fill="none" stroke="url(#auth-logo-grad)" strokeWidth="2.5" opacity="0.7" />
      <path d="M60 14 L68 52 L106 60 L68 68 L60 106 L52 68 L14 60 L52 52 Z" fill="url(#auth-logo-grad)" opacity="0.92" />
      <path d="M60 30 L64 56 L90 60 L64 64 L60 90 L56 64 L30 60 L56 56 Z" fill="#071226" opacity="0.82" />
      <circle cx="60" cy="60" r="6" fill="#ffffff" />
      <circle cx="60" cy="60" r="3" fill="#071226" />
    </svg>
  )
}

export default function LandingPage({ initialMode = 'register' }) {
  const { token } = useSession()

  // Suppress the global blurred page overlay so the split panels read crisply.
  useEffect(() => {
    document.body.classList.add('auth-active')
    return () => document.body.classList.remove('auth-active')
  }, [])

  if (token) {
    return <Navigate replace to="/app" />
  }

  return (
    <main className="auth-shell">
      <section className="auth-brand-panel">
        <Link className="brandmark auth-brand-mark" to="/">
          <span className="brandmark-dot" />
          <span>
            Trip Architect
            <small>Travel planning workspace</small>
          </span>
        </Link>

        <div className="auth-brand-hero">
          <CompassMark />
          <h1 className="auth-brand-headline">Design the trip before you book it.</h1>
          <p className="auth-brand-sub">
            Compare routes, deepen the winning plan, and keep every decision in one workspace.
          </p>
        </div>

        <div className="auth-brand-foot">
          <Link to="/privacy">Privacy</Link>
          <Link to="/terms">Terms</Link>
          <a href="mailto:support@triparchitect.app">Support</a>
        </div>
      </section>

      <section className="auth-form-panel">
        <div className="auth-form-inner">
          <AuthPanel initialMode={initialMode} />
        </div>
      </section>
    </main>
  )
}
