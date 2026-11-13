/** Colours are CSS variables (see index.css) so light and dark themes share one set of class names. */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        paper: 'rgb(var(--paper) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        ink: 'rgb(var(--ink) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        line: 'rgb(var(--line) / <alpha-value>)',
        brand: 'rgb(var(--brand) / <alpha-value>)',
        'brand-fg': 'rgb(var(--brand-fg) / <alpha-value>)',
        mark: 'rgb(var(--mark) / <alpha-value>)',
        ok: 'rgb(var(--ok) / <alpha-value>)',
        warn: 'rgb(var(--warn) / <alpha-value>)',
        bad: 'rgb(var(--bad) / <alpha-value>)',
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', '"Noto Sans"', '"Noto Sans Devanagari"', '"Noto Sans Telugu"', 'system-ui', 'sans-serif'],
        sans: ['"Noto Sans"', '"Noto Sans Devanagari"', '"Noto Sans Telugu"', 'system-ui', 'sans-serif'],
      },
      borderRadius: { field: '6px', panel: '10px' },
    },
  },
  plugins: [],
}
