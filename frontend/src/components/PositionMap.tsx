import { useEffect, useRef, useState } from 'react'
import type { RobotLiveState } from '../types'
import { toneVar, toneForStatus, STALE_MS } from '../status'
import './PositionMap.css'

const BOUND = 100
const VIEW_H = 420
const DEFAULT_VIEW_W = 900
const PAD = 24
const Y_TICK_STEP = 20

// Nice, round step sizes to snap the x-axis spacing to as the container resizes.
const NICE_STEPS = [2, 4, 5, 10, 20, 25, 50]

/**
 * Pick the x-axis tick step that makes grid cells read as squares in pixel
 * space: cell width (plotW / (span/xStep)) must equal cell height
 * (plotH / (span/yStep)), which reduces to xStep = yStep * (plotH / plotW).
 */
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

  return (
    <div className="position-map">
      <div className="panel-header">
        <h2>Fleet position</h2>
        <span className="panel-header__hint">x / y from latest telemetry</span>
      </div>
      <div className="position-map__canvas" ref={containerRef}>
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
                <text
                  x={cx}
                  y={cy - (emphasized ? 14 : 12)}
                  textAnchor="middle"
                  fontSize={emphasized ? 13 : 11}
                  fontWeight={isSelected ? 700 : 600}
                  fill={isSelected ? toneVar(tone) : 'var(--text-secondary)'}
                  opacity={stale ? 0.6 : 1}
                >
                  {r.id}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
