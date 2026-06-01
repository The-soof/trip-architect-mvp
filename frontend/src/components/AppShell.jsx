import { NavLink } from 'react-router-dom'
import { useSession } from '../hooks/useSession.jsx'

export default function AppShell({ title, subtitle, actions, children, compactHeader = false }) {
  const { user, clearSession } = useSession()

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar-nav">
          <NavLink className="brandmark" to="/">
            <span className="brandmark-dot" />
            <span>
              Trip Architect
              <small>Travel workspace</small>
            </span>
          </NavLink>
          <nav className="shell-nav">
            <NavLink className={({ isActive }) => (isActive ? 'active' : '')} to="/app">
              Workspace
            </NavLink>
            <NavLink className={({ isActive }) => (isActive ? 'active' : '')} to="/profile">
              Profile
            </NavLink>
          </nav>
        </div>
        <div className="topbar-meta">
          <div className="user-card">
            <p className="eyebrow">Traveler workspace</p>
            <strong>{user?.full_name || 'Traveler'}</strong>
            {user?.email ? <span>{user.email}</span> : null}
          </div>
          <button className="ghost-button topbar-logout" onClick={clearSession} type="button">
            Sign out
          </button>
        </div>
      </header>

      <main id="main-content">
        <section
          className={`page-intro surface-card${actions ? ' has-actions' : ''}${compactHeader ? ' page-intro-compact' : ''}`}
        >
          <div className="page-intro-copy">
            <p className="eyebrow">Trip workspace</p>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
          {actions ? <div className="page-actions">{actions}</div> : null}
        </section>

        {children}
      </main>

      <footer className="site-footer">
        <p>Structured planning, itinerary depth, and booking discovery in one workspace.</p>
        <div className="footer-links">
          <NavLink to="/privacy">Privacy</NavLink>
          <NavLink to="/terms">Terms</NavLink>
          <a href="mailto:support@triparchitect.app">Support</a>
        </div>
      </footer>
    </div>
  )
}
