export type RobotStatus =
  | 'IDLE'
  | 'MOVING'
  | 'STOPPED'
  | 'CHARGING'
  | 'LOW_BATTERY'
  | 'OVERHEATING'
  | 'ERROR'
  | 'NETWORK_ERROR'
  | 'MOTOR_ERROR'
  | 'OBSTACLE_DETECTED'
  | 'OFFLINE'

export const FAILURE_STATUSES: ReadonlySet<RobotStatus> = new Set([
  'ERROR',
  'NETWORK_ERROR',
  'MOTOR_ERROR',
  'OBSTACLE_DETECTED',
  'OFFLINE',
])

export interface Robot {
  id: string
  status: RobotStatus
  battery: number
  created_at: string
}

export interface TelemetryEvent {
  id: string
  battery: number
  temperature: number
  x: number
  y: number
  speed?: number
  status?: RobotStatus
}

export interface TelemetryRecord {
  id: number
  robot_id: string
  battery: number
  temperature: number
  x: number
  y: number
  timestamp: string
}

export interface TelemetrySample {
  battery: number
  temperature: number
  x: number
  y: number
  speed?: number
  status?: RobotStatus
  receivedAt: number
}

/** Live view of one robot: REST-seeded identity + a rolling window of telemetry. */
export interface RobotLiveState {
  id: string
  status: RobotStatus
  battery: number
  temperature: number | null
  x: number
  y: number
  /** Only known from the live WS feed — REST telemetry history doesn't persist it. */
  speed: number | null
  history: TelemetrySample[]
  lastUpdated: number | null
}

export type WSMessage = { type: 'telemetry'; robot: TelemetryEvent }
