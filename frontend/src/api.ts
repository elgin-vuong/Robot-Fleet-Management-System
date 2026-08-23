import type { Robot, TelemetryRecord } from './types'

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url} -> ${res.status}`)
  return res.json() as Promise<T>
}

export function fetchRobots(): Promise<Robot[]> {
  return getJSON<Robot[]>('/robots')
}

export function fetchRobotTelemetry(robotId: string, limit = 30): Promise<TelemetryRecord[]> {
  return getJSON<TelemetryRecord[]>(`/robots/${robotId}/telemetry?limit=${limit}`)
}

export async function sendCommand(robotId: string, command: 'START' | 'STOP'): Promise<void> {
  const res = await fetch(`/robots/${robotId}/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command }),
  })
  if (!res.ok) throw new Error(`command ${command} for ${robotId} -> ${res.status}`)
}
