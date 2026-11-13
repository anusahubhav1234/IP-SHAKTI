import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const ThemeContext = createContext(null)
export const useTheme = () => useContext(ThemeContext)

const read = () => document.documentElement.getAttribute('data-theme') || 'light'

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(read)
  const setTheme = useCallback((t) => {
    document.documentElement.setAttribute('data-theme', t)
    try { localStorage.setItem('sakti.theme', t) } catch { /* ignore */ }
    setThemeState(t)
  }, [])
  const toggle = useCallback(() => setTheme(theme === 'dark' ? 'light' : 'dark'), [theme, setTheme])
  useEffect(() => { document.documentElement.setAttribute('data-theme', theme) }, [theme])
  const value = useMemo(() => ({ theme, setTheme, toggle }), [theme, setTheme, toggle])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
