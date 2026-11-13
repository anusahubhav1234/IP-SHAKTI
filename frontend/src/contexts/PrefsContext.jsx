import { createContext, useCallback, useContext, useMemo, useState } from 'react'

const KEY = 'sakti.prefs'
const DEFAULTS = { mode: 'hybrid', topK: 5 }
const PrefsContext = createContext(null)
export const usePrefs = () => useContext(PrefsContext)

function load() {
  try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') } } catch { return DEFAULTS }
}

/** Per-browser retrieval preferences. The answer language lives on the user profile instead. */
export function PrefsProvider({ children }) {
  const [prefs, setPrefsState] = useState(load)
  const setPrefs = useCallback((patch) => {
    setPrefsState((p) => {
      const next = { ...p, ...patch }
      try { localStorage.setItem(KEY, JSON.stringify(next)) } catch { /* ignore */ }
      return next
    })
  }, [])
  const value = useMemo(() => ({ prefs, setPrefs }), [prefs, setPrefs])
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>
}
