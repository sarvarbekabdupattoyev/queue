import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api, getToken, setToken } from '../api/client'
import type { Role, TokenResponse, User } from '../api/types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (phone: string, password: string) => Promise<User>
  registerOwner: (data: {
    first_name: string
    last_name: string
    phone: string
    password: string
  }) => Promise<User>
  logout: () => void
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function homeFor(role: Role): string {
  if (role === 'manager') return '/manager'
  if (role === 'scanner') return '/scanner'
  return '/dashboard'
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null)
      return
    }
    try {
      setUser(await api<User>('/auth/me'))
    } catch {
      setUser(null)
    }
  }, [])

  useEffect(() => {
    refresh().finally(() => setLoading(false))
  }, [refresh])

  const login = useCallback(async (phone: string, password: string) => {
    const data = await api<TokenResponse>('/auth/login', { body: { phone, password } })
    setToken(data.access_token)
    setUser(data.user)
    return data.user
  }, [])

  const registerOwner = useCallback(
    async (payload: { first_name: string; last_name: string; phone: string; password: string }) => {
      const data = await api<TokenResponse>('/auth/register', { body: payload })
      setToken(data.access_token)
      setUser(data.user)
      return data.user
    },
    [],
  )

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    window.location.assign('/login')
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, registerOwner, logout, refresh }),
    [user, loading, login, registerOwner, logout, refresh],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
