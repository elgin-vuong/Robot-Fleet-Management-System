import type { Health } from '../status'
import './StatusBadge.css'

const LABEL: Record<Health, string> = {
  good: 'Good',
  warning: 'Warning',
  critical: 'Critical',
  offline: 'Offline',
}

const VAR: Record<Health, string> = {
  good: 'var(--status-good)',
  warning: 'var(--status-warning)',
  critical: 'var(--status-critical)',
  offline: 'var(--status-offline)',
}

export function HealthBadge({ health }: { health: Health }) {
  return (
    <span className="status-badge" style={{ color: VAR[health] }}>
      <span aria-hidden="true" className="status-badge_dot">
        ●
      </span>
      {LABEL[health]}
    </span>
  )
}
