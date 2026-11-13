import { useMemo } from 'react'
import { useTheme } from '../contexts/ThemeContext'

/** Recharts needs concrete colours; read them from the CSS variables of the active theme. */
export function useChartColors() {
  const { theme } = useTheme()
  return useMemo(() => {
    const css = getComputedStyle(document.documentElement)
    const c = (name) => `rgb(${css.getPropertyValue(name).trim().split(/\s+/).join(',')})`
    return { brand: c('--brand'), mark: c('--mark'), ink: c('--ink'), muted: c('--muted'), line: c('--line'),
             ok: c('--ok'), warn: c('--warn'), bad: c('--bad'), surface: c('--surface') }
  }, [theme])
}
