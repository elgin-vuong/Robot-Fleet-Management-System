import type { RobotLiveState } from '../types'
import { StatusBadge } from './StatusBadge'
import { HealthBadge } from './HealthBadge'
import { STALE_MS, deriveStatus } from '../status'
import './FleetTable.css'

function timeAgo(ts: number | null, now: number): string {
  if (ts == null) return '—'
  const secs = Math.round((now - ts) / 1000)
  if (secs < 2) return 'just now'
  if (secs < 60) return `${secs}s ago`
  return `${Math.round(secs / 60)}m ago`
}

interface Props {
  robots: RobotLiveState[]
  now: number
  selectedId: string | null
  onSelect: (id: string) => void
}

export function FleetTable({ robots, now, selectedId, onSelect }: Props) {
  if (robots.length === 0) {
    return (
      <div className="fleet-table fleet-table--empty">
        <p>No robots match the current filter.</p>
      </div>
    )
  }

  return (
    <div className="fleet-table">
      <table>
        <thead>
          <tr>
            <th scope="col">Robot</th>
            <th scope="col">State</th>
            <th scope="col">Health</th>
            <th scope="col" className="num">
              Battery
            </th>
            <th scope="col" className="num">
              Temp °C
            </th>
            <th scope="col">Last seen</th>
          </tr>
        </thead>
        <tbody>
          {robots.map((r) => {
            const stale = r.lastUpdated == null || now - r.lastUpdated > STALE_MS
            const { health } = deriveStatus(r.status)
            const isSelected = r.id === selectedId
            return (
              <tr
                key={r.id}
                className={[stale ? 'is-stale' : '', isSelected ? 'is-selected' : ''].join(' ').trim()}
                onClick={() => onSelect(r.id)}
                aria-selected={isSelected}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onSelect(r.id)
                  }
                }}
              >
                <th scope="row">{r.id}</th>
                <td>
                  <StatusBadge status={r.status} />
                </td>
                <td>
                  <HealthBadge health={health} />
                </td>
                <td className="num tabular">{r.battery.toFixed(0)}%</td>
                <td className="num tabular">{r.temperature != null ? r.temperature.toFixed(1) : '—'}</td>
                <td className="tabular">
                  {stale && <span className="stale-dot" aria-hidden="true" />}
                  {timeAgo(r.lastUpdated, now)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
