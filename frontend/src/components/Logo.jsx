export function Logo({ className = '' }) {
  return (
    <span className={`inline-flex items-center gap-2 font-display text-lg font-bold ${className}`}>
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="7" fill="rgb(var(--brand))" />
        <rect x="7" y="19" width="18" height="5" rx="1" fill="rgb(var(--mark))" />
        <path d="M9 9h14M9 14h10" stroke="rgb(var(--brand-fg))" strokeWidth="2.4" strokeLinecap="round" />
      </svg>
      IP-SAKTI Sahayaka
    </span>
  )
}
