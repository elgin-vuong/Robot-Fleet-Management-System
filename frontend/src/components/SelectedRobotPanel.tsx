import { useState } from 'react'
import type { RobotLiveState } from '../types'
import { FAILURE_STATUSES } from '../types'
import { STALE_MS, deriveStatus, toneVar, toneForStatus } from '../status'
import { HealthBadge } from './HealthBadge'
import { Sparkline } from './Sparkline'
import { sendCommand } from '../api'
import './SelectedRobotPanel.css'

function timeAgo(ts: number | null, now: number): string {
  if (ts == null) return '—'
  const secs = Math.round((now - ts) / 1000)
  if (secs < 2) return 'just now'
  if (secs < 60) return `${secs}s ago`
  return `${Math.round(secs / 60)}m ago`
}

function CommandButtons({ robot }: { robot: RobotLiveState }) {
  const [pending, setPending] = useState<'START' | 'STOP' | null>(null)
  const disabled = FAILURE_STATUSES.has(robot.status)

  const run = async (command: 'START' | 'STOP') => {
    setPending(command)
    try {
      await sendCommand(robot.id, command)
    } catch (err) {
      console.error(err)
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="command-buttons">
      <button
        type="button"
        className="command-buttons_btn"
        disabled={disabled || robot.status === 'MOVING' || pending !== null}
        onClick={() => run('START')}
        title={disabled ? 'Robot needs a reset before it can be commanded' : 'Start'}
      >
        {pending === 'START' ? '…' : 'Start'}
      </button>
      <button
        type="button"
        className="command-buttons_btn"
        disabled={disabled || robot.status === 'STOPPED' || pending !== null}
        onClick={() => run('STOP')}
        title={disabled ? 'Robot needs a reset before it can be commanded' : 'Stop'}
      >
        {pending === 'STOP' ? '…' : 'Stop'}
      </button>
    </div>
  )
}

export function SelectedRobotPanel({ robot, now }: { robot: RobotLiveState | null; now: number }) {
  if (!robot) {
    return (
      <div className="robot-panel robot-panel--empty">
        <p style={{ fontSize: '14px' }}>Select a robot from the table or map to see its performance.</p>
      </div>
    )
  }

  const { state, health, issue } = deriveStatus(robot.status)
  const stale = robot.lastUpdated == null || now - robot.lastUpdated > STALE_MS
  const tone = toneForStatus(robot.status)

  return (
    <div className="robot-panel">
      <div className="robot-panel_header">
        <h2>{robot.id}</h2>
        <HealthBadge health={health} />
      </div>

      <dl className="robot-panel_facts">
        <div>
          <dt>State</dt>
          <dd>{state}</dd>
        </div>
        <div>
          <dt>Issue</dt>
          <dd style={{ color: issue ? toneVar(tone) : undefined }}>{issue ?? 'None'}</dd>
        </div>
        <div>
          <dt>Battery</dt>
          <dd className="tabular">{robot.battery.toFixed(0)}%</dd>
        </div>
        <div>
          <dt>Temperature</dt>
          <dd className="tabular">{robot.temperature != null ? `${robot.temperature.toFixed(1)}°C` : '—'}</dd>
        </div>
        <div>
          <dt>Position</dt>
          <dd className="tabular">
            ({robot.x.toFixed(1)}, {robot.y.toFixed(1)})
          </dd>
        </div>
        <div>
          <dt>Speed</dt>
          <dd className="tabular">{robot.speed != null ? robot.speed.toFixed(1) : '—'}</dd>
        </div>
        <div>
          <dt>Last seen</dt>
          <dd className={stale ? 'is-stale' : undefined}>{timeAgo(robot.lastUpdated, now)}</dd>
        </div>
      </dl>

      <div className="robot-panel_charts">
        <div className="robot-panel_chart">
          <div className="robot-panel_chart-header">
            <h3>Battery history</h3>
            <span className="tabular">{robot.battery.toFixed(0)}%</span>
          </div>
          <Sparkline history={robot.history} field="battery" color="var(--series-1)" domain={[0, 100]} width={360} height={72} />
        </div>

        <div className="robot-panel_chart">
          <div className="robot-panel_chart-header">
            <h3>Temperature history</h3>
            <span className="tabular">{robot.temperature != null ? `${robot.temperature.toFixed(1)}°C` : '—'}</span>
          </div>
          <Sparkline history={robot.history} field="temperature" color="var(--series-2)" width={360} height={72} />
        </div>
      </div>

      <div className="robot-panel_commands">
        <h3>Commands</h3>
        <CommandButtons robot={robot} />
      </div>
    </div>
  )
}
