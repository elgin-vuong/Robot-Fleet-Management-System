import { useMemo } from 'react'
import type { RobotLiveState } from '../types'
import { toneForStatus } from '../status'
import type { ConnectionStatus } from '../useFleet'
import type { FleetFilter } from '../App'
import './FleetSummary.css'

interface Props {
  robots: RobotLiveState[]
  connection: ConnectionStatus
  filter: FleetFilter
  onFilterChange: (filter: FleetFilter) => void
}

export function FleetSummary({ robots, connection, filter, onFilterChange }: Props) {
  const stats = useMemo(() => {
    const total = robots.length
    let active = 0
    let attention = 0
    let offline = 0
    let batterySum = 0

    for (const r of robots) {
      const tone = toneForStatus(r.status)
      if (tone === 'offline') offline += 1
      else if (tone === 'warning' || tone === 'serious' || tone === 'critical') attention += 1
      else active += 1
      batterySum += r.battery
    }

    return {
      total,
      active,
      attention,
      offline,
      avgBattery: total ? batterySum / total : 0,
    }
  }, [robots])

  const toggleFilter = (next: FleetFilter) => {
    onFilterChange(filter === next ? 'all' : next)
  }

  return (
    <div className="fleet-summary">
      <button
        type="button"
        className={`stat-tile ${filter === 'all' ? 'stat-tile--active' : ''}`}
        onClick={() => onFilterChange('all')}
      >
        <span className="stat-tile_label">Fleet</span>
        <span className="stat-tile_value">{stats.total}</span>
      </button>
      <button
        type="button"
        className={`stat-tile ${filter === 'active' ? 'stat-tile--active' : ''}`}
        onClick={() => toggleFilter('active')}
      >
        <span className="stat-tile_label">Active</span>
        <span className="stat-tile_value" style={{ color: 'var(--status-good)' }}>
          {stats.active}
        </span>
      </button>
      <button
        type="button"
        className={`stat-tile ${filter === 'attention' ? 'stat-tile--active' : ''}`}
        onClick={() => toggleFilter('attention')}
        disabled={stats.attention === 0}
      >
        <span className="stat-tile_label">Needs attention</span>
        <span className="stat-tile_value" style={{ color: stats.attention ? 'var(--status-warning)' : undefined }}>
          {stats.attention}
        </span>
      </button>
      <button
        type="button"
        className={`stat-tile ${filter === 'offline' ? 'stat-tile--active' : ''}`}
        onClick={() => toggleFilter('offline')}
        disabled={stats.offline === 0}
      >
        <span className="stat-tile_label">Offline</span>
        <span className="stat-tile_value" style={{ color: stats.offline ? 'var(--status-offline)' : undefined }}>
          {stats.offline}
        </span>
      </button>
      <div className="stat-tile">
        <span className="stat-tile_label">Avg battery</span>
        <span className="stat-tile_value">{stats.avgBattery.toFixed(0)}%</span>
      </div>
      <div className="stat-tile stat-tile--connection">
        <span className="stat-tile_label">Feed</span>
        <span className={`connection-pill connection-pill--${connection}`}>
          <span className="connection-pill_dot" aria-hidden="true" />
          {connection === 'open' ? 'Live' : connection === 'connecting' ? 'Connecting…' : 'Reconnecting…'}
        </span>
      </div>
    </div>
  )
}
