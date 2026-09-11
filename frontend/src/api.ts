import type { Robot, TelemetryRecord } from './types'

async function getJSON<T>(url: string, token: string): Promise<T> {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) throw new Error(`${url} -> ${res.status}`)
  return res.json() as Promise<T>
}

export function fetchRobots(token: string): Promise<Robot[]> {
  return getJSON<Robot[]>('/robots', token)
}

export function fetchRobotTelemetry(robotId: string, token: string, limit = 30): Promise<TelemetryRecord[]> {
  return getJSON<TelemetryRecord[]>(`/robots/${robotId}/telemetry?limit=${limit}`, token)
}

export async function sendCommand(robotId: string, command: 'START' | 'STOP', token: string): Promise<void> {
  const res = await fetch(`/robots/${robotId}/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ command }),
  })
  if (!res.ok) throw new Error(`command ${command} for ${robotId} -> ${res.status}`)
}
