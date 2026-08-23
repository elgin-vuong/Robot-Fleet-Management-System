import { useCallback, useEffect, useReducer, useRef } from 'react'
import { fetchRobotTelemetry, fetchRobots } from './api'
import type { RobotLiveState, TelemetryEvent, TelemetrySample, WSMessage } from './types'

const HISTORY_LIMIT = 40
const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 15000

export type ConnectionStatus = 'connecting' | 'open' | 'closed'

interface FleetState {
  robots: Record<string, RobotLiveState>
  order: string[]
  connection: ConnectionStatus
}

type Action =
  | { type: 'seed'; robots: RobotLiveState[] }
  | { type: 'telemetry'; event: TelemetryEvent }
  | { type: 'connection'; status: ConnectionStatus }

function pushSample(history: TelemetrySample[], sample: TelemetrySample): TelemetrySample[] {
  const next = history.length >= HISTORY_LIMIT ? history.slice(1) : history.slice()
  next.push(sample)
  return next
}

function reducer(state: FleetState, action: Action): FleetState {
  switch (action.type) {
    case 'seed': {
      const robots: Record<string, RobotLiveState> = {}
      const order: string[] = []
      for (const r of action.robots) {
        robots[r.id] = r
        order.push(r.id)
      }
      order.sort()
      return { ...state, robots, order }
    }
    case 'telemetry': {
      const { event } = action
      const existing = state.robots[event.id]
      const sample: TelemetrySample = {
        battery: event.battery,
        temperature: event.temperature,
        x: event.x,
        y: event.y,
        speed: event.speed,
        status: event.status,
        receivedAt: Date.now(),
      }

      const updated: RobotLiveState = existing
        ? {
            ...existing,
            status: event.status ?? existing.status,
            battery: event.battery,
            temperature: event.temperature,
            x: event.x,
            y: event.y,
            speed: event.speed ?? existing.speed,
            history: pushSample(existing.history, sample),
            lastUpdated: sample.receivedAt,
          }
        : {
            id: event.id,
            status: event.status ?? 'IDLE',
            battery: event.battery,
            temperature: event.temperature,
            x: event.x,
            y: event.y,
            speed: event.speed ?? null,
            history: [sample],
            lastUpdated: sample.receivedAt,
          }

      const isNew = !existing
      const order = isNew ? [...state.order, event.id].sort() : state.order

      return {
        ...state,
        order,
        robots: { ...state.robots, [event.id]: updated },
      }
    }
    case 'connection':
      return { ...state, connection: action.status }
    default:
      return state
  }
}

export function useFleet() {
  const [state, dispatch] = useReducer(reducer, { robots: {}, order: [], connection: 'connecting' })
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef(RECONNECT_BASE_MS)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const seed = useCallback(async () => {
    try {
      const robots = await fetchRobots()
      const seeded = await Promise.all(
        robots.map(async (r): Promise<RobotLiveState> => {
          let history: TelemetrySample[] = []
          try {
            const records = await fetchRobotTelemetry(r.id, HISTORY_LIMIT)
            history = records
              .slice()
              .reverse()
              .map((t) => ({
                battery: t.battery,
                temperature: t.temperature,
                x: t.x,
                y: t.y,
                receivedAt: new Date(t.timestamp).getTime(),
              }))
          } catch {
            // No telemetry yet for this robot — fine, it'll fill in live.
          }

          const last = history[history.length - 1]
          return {
            id: r.id,
            status: r.status,
            battery: r.battery,
            temperature: last?.temperature ?? null,
            x: last?.x ?? 0,
            y: last?.y ?? 0,
            // Not persisted in REST telemetry history — only arrives live over WS.
            speed: null,
            history,
            lastUpdated: last?.receivedAt ?? null,
          }
        }),
      )
      dispatch({ type: 'seed', robots: seeded })
    } catch (err) {
      console.error('Failed to seed fleet from REST API', err)
    }
  }, [])

  useEffect(() => {
    seed()
  }, [seed])

  useEffect(() => {
    let cancelled = false

    const connect = () => {
      if (cancelled) return
      dispatch({ type: 'connection', status: 'connecting' })

      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${proto}//${window.location.host}/ws/robots`)
      wsRef.current = ws

      ws.onopen = () => {
        retryRef.current = RECONNECT_BASE_MS
        dispatch({ type: 'connection', status: 'open' })
      }

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data) as WSMessage
          if (msg.type === 'telemetry') {
            dispatch({ type: 'telemetry', event: msg.robot })
          }
        } catch (err) {
          console.error('Bad WS payload', err)
        }
      }

      const scheduleReconnect = () => {
        if (cancelled) return
        dispatch({ type: 'connection', status: 'closed' })
        const delay = retryRef.current
        retryRef.current = Math.min(delay * 2, RECONNECT_MAX_MS)
        timerRef.current = setTimeout(connect, delay)
      }

      ws.onclose = scheduleReconnect
      ws.onerror = () => ws.close()
    }

    connect()

    return () => {
      cancelled = true
      if (timerRef.current) clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [])

  return state
}
