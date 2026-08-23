import { useEffect, useMemo, useState } from 'react'
import { useFleet } from './useFleet'
import { FleetSummary } from './components/FleetSummary'
import { FleetTable } from './components/FleetTable'
import { PositionMap } from './components/PositionMap'
import { SelectedRobotPanel } from './components/SelectedRobotPanel'
import { toneForStatus } from './status'
import './App.css'

export type FleetFilter = 'all' | 'active' | 'attention' | 'offline'

function App() {
  const { robots, order, connection } = useFleet()
  const [now, setNow] = useState(() => Date.now())
  const [filter, setFilter] = useState<FleetFilter>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  const robotList = useMemo(() => order.map((id) => robots[id]).filter(Boolean), [order, robots])

  const filteredList = useMemo(() => {
    if (filter === 'all') return robotList
    return robotList.filter((r) => {
      const tone = toneForStatus(r.status)
      if (filter === 'active') return tone === 'good' || tone === 'neutral'
      if (filter === 'attention') return tone === 'warning' || tone === 'serious' || tone === 'critical'
      if (filter === 'offline') return tone === 'offline'
      return true
    })
  }, [robotList, filter])

  // Keep selection valid; default to the first visible robot once data arrives.
  useEffect(() => {
    if (selectedId && robotList.some((r) => r.id === selectedId)) return
    setSelectedId(filteredList[0]?.id ?? robotList[0]?.id ?? null)
  }, [robotList, filteredList, selectedId])

  const selectedRobot = selectedId ? (robots[selectedId] ?? null) : null

  return (
    <div className="app">
      <header className="app__header">
        <h1>Robot Fleet Dashboard</h1>
        <p>Live telemetry over WebSocket, backed by Kafka + Redis.</p>
      </header>

      <FleetSummary robots={robotList} connection={connection} filter={filter} onFilterChange={setFilter} />

      <FleetTable robots={filteredList} now={now} selectedId={selectedId} onSelect={setSelectedId} />

      <SelectedRobotPanel robot={selectedRobot} now={now} />

      <PositionMap robots={robotList} now={now} selectedId={selectedId} onSelect={setSelectedId} />
    </div>
  )
}

export default App
