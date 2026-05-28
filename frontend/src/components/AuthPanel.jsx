import { useState } from 'react'
import { apiRequest } from '../api/client'
import { useSession } from '../hooks/useSession.jsx'

const DEFAULT_REGISTER = {
  email: '',
  full_name: '',
  password: '',
}

const DEFAULT_LOGIN = {
  email: '',
  password: '',
}

export default function AuthPanel() {
  const { setSession } = useSession()
  const [mode, setMode] = useState('register')
  const [registerForm, setRegisterForm] = useState(DEFAULT_REGISTER)
  const [loginForm, setLoginForm] = useState(DEFAULT_LOGIN)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const payload = mode === 'register' ? registerForm : loginForm
      const endpoint = mode === 'register' ? '/auth/register' : '/auth/login'
      const data = await apiRequest(endpoint, {
        method: 'POST',
        body: payload,
      })
      setSession({ token: data.access_token, user: data.user })
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="auth-panel">
      <div className="panel-switch">
        <button className={mode === 'register' ? 'active' : ''} onClick={() => setMode('register')} type="button">
          Create account
        </button>
        <button className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')} type="button">
          Sign in
        </button>
      </div>

      <form className="auth-form" onSubmit={handleSubmit}>
        {mode === 'register' && (
          <label>
            Full name
            <input
              value={registerForm.full_name}
              onChange={(event) => setRegisterForm({ ...registerForm, full_name: event.target.value })}
              placeholder="Dylan Parker"
              required
            />
          </label>
        )}
        <label>
          Email
          <input
            value={mode === 'register' ? registerForm.email : loginForm.email}
            onChange={(event) =>
              mode === 'register'
                ? setRegisterForm({ ...registerForm, email: event.target.value })
                : setLoginForm({ ...loginForm, email: event.target.value })
            }
            placeholder="dylan@example.com"
            type="email"
            required
          />
        </label>
        <label>
          Password
          <input
            value={mode === 'register' ? registerForm.password : loginForm.password}
            onChange={(event) =>
              mode === 'register'
                ? setRegisterForm({ ...registerForm, password: event.target.value })
                : setLoginForm({ ...loginForm, password: event.target.value })
            }
            placeholder="At least 8 characters"
            type="password"
            required
          />
        </label>

        {error ? <p className="inline-error">{error}</p> : null}

        <button className="primary-button" disabled={loading} type="submit">
          {loading ? 'Working...' : mode === 'register' ? 'Start planning' : 'Continue planning'}
        </button>
      </form>
    </section>
  )
}
