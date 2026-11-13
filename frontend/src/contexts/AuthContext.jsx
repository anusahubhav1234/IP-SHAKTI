import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { authApi, tokenStore } from '../services/api'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(Boolean(tokenStore.get()))

  useEffect(() => {
    if (!tokenStore.get()) return
    authApi.me().then(setUser).catch(() => tokenStore.clear()).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener('sakti:unauthorized', onUnauthorized)
    return () => window.removeEventListener('sakti:unauthorized', onUnauthorized)
  }, [])

  const login = useCallback(async (email, password) => {
    const res = await authApi.login({ email, password })
    tokenStore.set(res.access_token)
    setUser(res.user)
    return res.user
  }, [])

  const register = useCallback(async ({ email, password, full_name }) => {
    await authApi.register({ email, password, full_name })
    return login(email, password)
  }, [login])

  const logout = useCallback(async () => {
    await authApi.logout()
    tokenStore.clear()
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, setUser, loading, login, register, logout, isAdmin: user?.role === 'admin' }),
    [user, loading, login, register, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
