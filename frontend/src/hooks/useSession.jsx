import { createContext, useContext, useMemo, useState } from 'react'

const STORAGE_KEY = 'trip-architect-session'
const SessionContext = createContext(null)

function loadSession() {
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) {
    return { token: null, user: null }
  }
  try {
    return JSON.parse(raw)
  } catch {
    return { token: null, user: null }
  }
}

export function SessionProvider({ children }) {
  const [session, setSession] = useState(loadSession)

  const value = useMemo(
    () => ({
      ...session,
      setSession(nextSession) {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextSession))
        setSession(nextSession)
      },
      clearSession() {
        window.localStorage.removeItem(STORAGE_KEY)
        setSession({ token: null, user: null })
      },
    }),
    [session],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession() {
  const context = useContext(SessionContext)
  if (!context) {
    throw new Error('useSession must be used inside SessionProvider')
  }
  return context
}
