import { Link } from 'react-router-dom'
import { useSession } from '../hooks/useSession.jsx'

export default function AppShell({ title, subtitle, actions, children }) {
  const { user, clearSession } = useSession()

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-nav">
          <Link className="brandmark" to="/app">
            <span className="brandmark-dot" />
            Trip Architect
          </Link>
          <nav className="shell-nav">
            <Link to="/app">Workspace</Link>
            <Link to="/profile">Profile</Link>
          </nav>
        </div>
        <div className="topbar-meta">
          <div>
            <p className="eyebrow">Traveler workspace</p>
            <strong>{user?.full_name}</strong>
          </div>
          <button className="ghost-button" onClick={clearSession} type="button">
            Sign out
          </button>
        </div>
      </header>

      <section className="page-intro">
        <div>
          <p className="eyebrow">AI trip planner</p>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        {actions ? <div className="page-actions">{actions}</div> : null}
      </section>

      {children}
    </div>
  )
}
