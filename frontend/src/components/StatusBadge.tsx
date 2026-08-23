import type { RobotStatus } from '../types'
import { toneForStatus, toneVar } from '../status'
import './StatusBadge.css'

const DOT = '●'

export function StatusBadge({ status }: { status: RobotStatus }) {
  const tone = toneForStatus(status)
  const color = toneVar(tone)
  const label = status.replaceAll('_', ' ')

  return (
    <span className="status-badge" style={{ color }}>
      <span aria-hidden="true" className="status-badge__dot">
        {DOT}
      </span>
      {label}
    </span>
  )
}
