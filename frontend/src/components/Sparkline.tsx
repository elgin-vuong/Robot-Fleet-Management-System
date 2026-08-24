import { useMemo } from 'react'
import type { TelemetrySample } from '../types'

interface SparklineProps {
  history: TelemetrySample[]
  field: 'battery' | 'temperature'
  color: string
  width?: number
  height?: number
  domain?: [number, number]
}

export function Sparkline({ history, field, color, width = 96, height = 28, domain }: SparklineProps) {
  const { path, lastPoint } = useMemo(() => {
    const values = history.map((s) => s[field]).filter((v): v is number => v != null)
    if (values.length < 2) return { path: '', lastPoint: null }

    const [min, max] = domain ?? [Math.min(...values), Math.max(...values)]
    const span = max - min || 1
    const pad = 3

    const points = values.map((v, i) => {
      const x = (i / (values.length - 1)) * (width - pad * 2) + pad
      const y = height - pad - ((v - min) / span) * (height - pad * 2)
      return [x, y] as const
    })

    const d = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
    return { path: d, lastPoint: points[points.length - 1] }
  }, [history, field, domain, width, height])

  if (!path) {
    return (
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Not enough data yet">
        <text x={width / 2} y={height / 2 + 4} textAnchor="middle" fontSize="10" fill="var(--text-muted)">
          —
        </text>
      </svg>
    )
  }

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${field} trend`}>
      <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      {lastPoint && <circle cx={lastPoint[0]} cy={lastPoint[1]} r={2.5} fill={color} />}
    </svg>
  )
}
