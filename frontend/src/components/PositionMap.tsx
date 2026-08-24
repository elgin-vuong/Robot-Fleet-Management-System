import { useEffect, useRef, useState } from 'react'
import type { RobotLiveState } from '../types'
import { toneVar, toneForStatus, deriveStatus, STALE_MS } from '../status'
import './PositionMap.css'

const BOUND = 100
const VIEW_H = 420
const DEFAULT_VIEW_W = 900
const PAD = 24
const Y_TICK_STEP = 20

const NICE_STEPS = [2, 4, 5, 10, 20, 25, 50]

function xTickStepFor(plotW: number, plotH: number) {
  const target = (Y_TICK_STEP * plotH) / plotW
  return NICE_STEPS.reduce((best, step) => (Math.abs(step - target) < Math.abs(best - target) ? step : best))
}

function makeProjectors(viewW: number) {
  const projectX = (v: number) => {
    const t = (v + BOUND) / (BOUND * 2)
    return PAD + t * (viewW - PAD * 2)
  }
  const projectY = (v: number) => {
    const t = (v + BOUND) / (BOUND * 2)
    return PAD + t * (VIEW_H - PAD * 2)
  }
  return { projectX, projectY }
}

interface Props {
  robots: RobotLiveState[]
  now: number
  selectedId: string | null
  onSelect: (id: string) => void
}

export function PositionMap({ robots, now, selectedId, onSelect }: Props) {
  const [hovered, setHovered] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [viewW, setViewW] = useState(DEFAULT_VIEW_W)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width
      if (width && width > 0) setViewW(width)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const { projectX, projectY } = makeProjectors(viewW)

  const plotW = viewW - PAD * 2
  const plotH = VIEW_H - PAD * 2
  const xTickStep = xTickStepFor(plotW, plotH)

  const xTicks: number[] = []
  for (let t = -BOUND; t <= BOUND; t += xTickStep) xTicks.push(t)

  const yTicks: number[] = []
  for (let t = -BOUND; t <= BOUND; t += Y_TICK_STEP) yTicks.push(t)

  const hoveredRobot = robots.find((r) => r.id === hovered) ?? null
  const tooltipX = hoveredRobot ? projectX(hoveredRobot.x) : 0
  const tooltipY = hoveredRobot ? projectY(-hoveredRobot.y) : 0

  const flipX = tooltipX > viewW - 140
  const flipY = tooltipY < 100
  const tooltipTransform = `translate(${flipX ? '-100%' : '0'}, ${flipY ? '12px' : 'calc(-100% - 12px)'})`

  return (
    <div className="position-map">
      <div className="panel-header">
        <h2>Fleet position</h2>
      </div>
      <div className="position-map_canvas" ref={containerRef}>
        <svg
          viewBox={`0 0 ${viewW} ${VIEW_H}`}
          preserveAspectRatio="none"
          role="img"
          aria-label="Robot positions on the fleet grid"
        >
          <rect x={0} y={0} width={viewW} height={VIEW_H} rx={8} fill="var(--surface-1)" />
          {xTicks.map((t) => (
            <line
              key={`v${t}`}
              x1={projectX(t)}
              y1={PAD}
              x2={projectX(t)}
              y2={VIEW_H - PAD}
              stroke="var(--gridline)"
              strokeWidth={1}
            />
          ))}
          {yTicks.map((t) => (
            <line
              key={`h${t}`}
              x1={PAD}
              y1={projectY(t)}
              x2={viewW - PAD}
              y2={projectY(t)}
              stroke="var(--gridline)"
              strokeWidth={1}
            />
          ))}
          <line
            x1={projectX(0)}
            y1={PAD}
            x2={projectX(0)}
            y2={VIEW_H - PAD}
            stroke="var(--baseline)"
            strokeWidth={1.5}
          />
          <line
            x1={PAD}
            y1={projectY(0)}
            x2={viewW - PAD}
            y2={projectY(0)}
            stroke="var(--baseline)"
            strokeWidth={1.5}
          />

          {robots.map((r) => {
            const stale = r.lastUpdated == null || now - r.lastUpdated > STALE_MS
            const tone = toneForStatus(r.status)
            const cx = projectX(r.x)
            const cy = projectY(-r.y)
            const isHovered = hovered === r.id
            const isSelected = r.id === selectedId
            const emphasized = isHovered || isSelected

            return (
              <g
                key={r.id}
                onMouseEnter={() => setHovered(r.id)}
                onMouseLeave={() => setHovered((h) => (h === r.id ? null : h))}
                onClick={() => onSelect(r.id)}
                style={{ cursor: 'pointer' }}
              >
                <circle cx={cx} cy={cy} r={16} fill="transparent" />
                {isSelected && (
                  <circle cx={cx} cy={cy} r={11} fill="none" stroke={toneVar(tone)} strokeWidth={1.5} opacity={0.5} />
                )}
                <circle
                  cx={cx}
                  cy={cy}
                  r={emphasized ? 8 : 6}
                  fill={toneVar(tone)}
                  opacity={stale ? 0.35 : 1}
                  stroke="var(--surface-1)"
                  strokeWidth={2}
                />
                
              </g>
            )
          })}
        </svg>
        {hoveredRobot && (
          <div
            className="position-map_tooltip"
            style={{
              left: tooltipX,
              top: tooltipY,
              transform: tooltipTransform,
            }}
          >
            <div className="position-map_tooltip-title" style={{ color: toneVar(toneForStatus(hoveredRobot.status)) }}>
              {hoveredRobot.id}
            </div>
            <div className="position-map_tooltip-row">
              <span>Status</span>
              <span>{deriveStatus(hoveredRobot.status).state}{deriveStatus(hoveredRobot.status).issue ? ` (${deriveStatus(hoveredRobot.status).issue})` : ''}</span>
            </div>
            <div className="position-map_tooltip-row">
              <span>Battery</span>
              <span>{hoveredRobot.battery != null ? `${Math.round(hoveredRobot.battery)}%` : '—'}</span>
            </div>
            <div className="position-map_tooltip-row">
              <span>Temp</span>
              <span>{hoveredRobot.temperature != null ? `${hoveredRobot.temperature.toFixed(1)}°C` : '—'}</span>
            </div>
            <div className="position-map_tooltip-row">
              <span>Speed</span>
              <span>{hoveredRobot.speed != null ? `${hoveredRobot.speed.toFixed(2)} m/s` : '—'}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
