import { useState, useEffect } from 'react'
import { Detection, DetectionReport, IssueType, PriorityLabel } from './types'
import MapView from './components/MapView'
import Sidebar from './components/Sidebar'

export default function App() {
  const [report, setReport] = useState<DetectionReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Detection | null>(null)
  const [filterPriority, setFilterPriority] = useState<PriorityLabel | 'ALL'>('ALL')
  const [filterType, setFilterType] = useState<IssueType | 'ALL'>('ALL')
  const [showHeatmap, setShowHeatmap] = useState(false)
  const [flyTo, setFlyTo] = useState<{ lat: number; lng: number; ts: number } | null>(null)

  useEffect(() => {
    fetch('/detections.json')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then((data: DetectionReport) => { setReport(data); setLoading(false) })
      .catch((e: Error) => { setError(e.message); setLoading(false) })
  }, [])

  const allDetections = report?.detections ?? []

  const filtered = allDetections.filter(d =>
    (filterPriority === 'ALL' || d.priority_label === filterPriority) &&
    (filterType === 'ALL' || d.type === filterType) &&
    d.lat !== null && d.lng !== null,
  )

  function handleRowClick(d: Detection) {
    setSelected(d)
    if (d.lat !== null && d.lng !== null) {
      setFlyTo({ lat: d.lat, lng: d.lng, ts: Date.now() })
    }
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-900">
        <div className="text-slate-300 text-lg animate-pulse">Loading detections…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-900 flex-col gap-2">
        <div className="text-red-400 text-lg font-semibold">Failed to load detections</div>
        <div className="text-slate-400 text-sm">{error}</div>
      </div>
    )
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-900">
      <Sidebar
        detections={filtered}
        allDetections={allDetections}
        selected={selected}
        filterPriority={filterPriority}
        filterType={filterType}
        onFilterPriority={setFilterPriority}
        onFilterType={setFilterType}
        onSelect={handleRowClick}
        showHeatmap={showHeatmap}
        onToggleHeatmap={() => setShowHeatmap(v => !v)}
      />
      <div className="flex-1 relative">
        <MapView
          detections={filtered}
          selected={selected}
          flyTo={flyTo}
          showHeatmap={showHeatmap}
          onSelect={setSelected}
        />
      </div>
    </div>
  )
}
