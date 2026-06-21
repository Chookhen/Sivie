import { useState, useEffect, useCallback } from 'react'
import { DetectionReport, ModelDataset, Occurrence } from './types'
import NavBar, { Page } from './components/NavBar'
import MapView from './components/MapView'
import AnalysisPage from './pages/AnalysisPage'
import DatabasePage from './pages/DatabasePage'
import ProcessingPage from './pages/ProcessingPage'
import { fetchOccurrences } from './api'

export default function App() {
  const [report, setReport] = useState<DetectionReport | null>(null)
  const [loading, setLoading] = useState(true)

  const [occurrences, setOccurrences] = useState<Occurrence[]>([])
  const [locationAvailable, setLocationAvailable] = useState(false)
  const [occError, setOccError] = useState<string | null>(null)
  const [backend, setBackend] = useState<string | undefined>(undefined)

  const [selected, setSelected] = useState<Occurrence | null>(null)
  const [flyTo, setFlyTo] = useState<{ lat: number; lng: number; ts: number } | null>(null)
  const [page, setPage] = useState<Page>('map')

  // Cache-busted so a freshly processed detections.json is always picked up.
  const loadReport = useCallback(() => {
    return fetch(`/detections.json?t=${Date.now()}`)
      .then(r => (r.ok ? r.json() : null))
      .then((data: DetectionReport | null) => { setReport(data) })
      .catch(() => { /* no detections yet */ })
  }, [])

  const loadOccurrences = useCallback(() => {
    return fetchOccurrences()
      .then(db => {
        setOccurrences(db.occurrences)
        setLocationAvailable(db.location_available)
        setBackend(db.backend)
        setOccError(null)
      })
      .catch(() => setOccError(`Backend offline — start it with: uvicorn server.app:app --port 8000`))
  }, [])

  useEffect(() => {
    loadReport().finally(() => setLoading(false))
  }, [loadReport])

  // Refetch occurrences whenever we navigate, so DB edits reflect on the map.
  useEffect(() => {
    loadOccurrences()
  }, [page, loadOccurrences])

  const models: ModelDataset[] = [
    {
      key: 'standard',
      label: 'YOLOv11-x',
      sublabel: 'X-Large · AI triage',
      detections: report?.detections ?? [],
    },
  ]

  function handleSelect(o: Occurrence | null) {
    setSelected(o)
    if (o && o.lat != null && o.lng != null) {
      setFlyTo({ lat: o.lat, lng: o.lng, ts: Date.now() })
    }
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-canvas">
        <div className="text-muted text-sm animate-pulse">Loading…</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-canvas">
      <NavBar
        page={page}
        onNavigate={setPage}
        status={{ online: !occError, backend, count: occurrences.length }}
      />
      {page === 'map' && (
        <div className="flex-1 relative min-h-0">
          {occError && (
            <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 bg-panel-2 border border-line text-muted text-xs rounded-md px-3 py-1.5 shadow-pop">
              {occError}
            </div>
          )}
          <MapView
            occurrences={occurrences}
            locationAvailable={locationAvailable}
            selected={selected}
            flyTo={flyTo}
            onSelect={handleSelect}
          />
        </div>
      )}
      {page === 'database' && <DatabasePage />}
      {page === 'analysis' && <AnalysisPage models={models} />}
      {page === 'processing' && (
        <ProcessingPage
          onNavigate={setPage}
          onProcessed={() => { loadReport(); loadOccurrences() }}
        />
      )}
    </div>
  )
}
