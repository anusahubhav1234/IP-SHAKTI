import { LANGUAGES } from '../utils/format'

export function LanguageSelect({ value, onChange, allowAuto = false, id, label = 'Answer language' }) {
  return (
    <select id={id} aria-label={label} className="field !w-auto !py-1.5" value={value || ''} onChange={(e) => onChange(e.target.value || null)}>
      {allowAuto && <option value="">Same as question</option>}
      {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.native}{l.native !== l.label ? ` (${l.label})` : ''}</option>)}
    </select>
  )
}
