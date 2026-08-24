import type { RobotStatus } from './types'

export type StatusTone = 'good' | 'warning' | 'serious' | 'critical' | 'offline' | 'neutral'

const TONE_BY_STATUS: Record<RobotStatus, StatusTone> = {
  IDLE: 'neutral',
  MOVING: 'good',
  STOPPED: 'neutral',
  CHARGING: 'good',
  LOW_BATTERY: 'warning',
  OVERHEATING: 'warning',
  ERROR: 'critical',
  NETWORK_ERROR: 'critical',
  MOTOR_ERROR: 'critical',
  OBSTACLE_DETECTED: 'serious',
  OFFLINE: 'offline',
}

export function toneForStatus(status: RobotStatus): StatusTone {
  return TONE_BY_STATUS[status] ?? 'neutral'
}

export function toneVar(tone: StatusTone): string {
  if (tone === 'neutral') return 'var(--text-muted)'
  return `var(--status-${tone})`
}

export const STALE_MS = 8000

/**
 * The backend only tracks a single `status` field that conflates operational
 * state (IDLE/MOVING/STOPPED/CHARGING) with health conditions (errors,
 * overheating, low battery). Until the API exposes them separately
 * (robot.state / robot.health / robot.current_issue), we derive a best-effort
 * split here. A robot's operational state while it's in a failure/health
 * condition isn't recoverable from this field alone — the simulator
 * overwrites `status` in place — so we surface that as "UNKNOWN" rather than
 * guess.
 */
export type Health = 'good' | 'warning' | 'critical' | 'offline'

export interface DerivedStatus {
  state: string
  health: Health
  issue: string | null
}

const OPERATIONAL_STATES: ReadonlySet<RobotStatus> = new Set(['IDLE', 'MOVING', 'STOPPED', 'CHARGING'])

const HEALTH_BY_TONE: Record<StatusTone, Health> = {
  good: 'good',
  neutral: 'good',
  warning: 'warning',
  serious: 'critical',
  critical: 'critical',
  offline: 'offline',
}

export function deriveStatus(status: RobotStatus): DerivedStatus {
  const tone = toneForStatus(status)
  const health = HEALTH_BY_TONE[tone]

  if (OPERATIONAL_STATES.has(status)) {
    return { state: status, health, issue: null }
  }

  return { state: 'UNKNOWN', health, issue: status }
}
