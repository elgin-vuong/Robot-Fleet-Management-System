import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { AuthUser } from './types'
import { login as loginRequest, fetchMe } from './authApi'

const TOKEN_STORAGE_KEY = 'fleet_auth_token'

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

interface AuthContextValue {
  token: string | null
  user: AuthUser | null
  status: AuthStatus
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY))
  const [user, setUser] = useState<AuthUser | null>(null)
  const [status, setStatus] = useState<AuthStatus>(token ? 'loading' : 'unauthenticated')

  // Whenever we have a token (fresh login, or restored from storage on page load),
  // resolve it against the server to get the real identity — never trust a stored
  // token blindly, since it may have expired.
  useEffect(() => {
    if (!token) {
      setStatus('unauthenticated')
      return
    }

    let cancelled = false
    setStatus('loading')

    fetchMe(token)
      .then((me) => {
        if (cancelled) return
        setUser(me)
        setStatus('authenticated')
      })
      .catch(() => {
        if (cancelled) return
        localStorage.removeItem(TOKEN_STORAGE_KEY)
        setToken(null)
        setUser(null)
        setStatus('unauthenticated')
      })

    return () => {
      cancelled = true
    }
  }, [token])

  const login = async (username: string, password: string) => {
    const newToken = await loginRequest(username, password)
    localStorage.setItem(TOKEN_STORAGE_KEY, newToken)
    setToken(newToken)
  }

  const logout = () => {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    setToken(null)
    setUser(null)
    setStatus('unauthenticated')
  }

  return <AuthContext.Provider value={{ token, user, status, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
