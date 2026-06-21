import { useRef, useEffect, useState } from 'react'
import Map, { Marker, Popup } from 'react-map-gl'
import type { MapRef } from 'react-map-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { Occurrence } from '../types'
import { scoreColor, scoreLabel } from '../api'

interface Props {
  occurrences: Occurrence[]
  locationAvailable: boolean
  selected: Occurrence | null
  flyTo: { lat: number; lng: number; ts: number } | null
  onSelect: (o: Occurrence | null) => void
}

export default function MapView({ occurrences, locationAvailable, selected, flyTo, onSelect }: Props) {
  const mapRef = useRef<MapRef | null>(null)
  const [mapLoaded, setMapLoaded] = useState(false)
  const token = import.meta.env.VITE_MAPBOX_TOKEN as string | undefined

  useEffect(() => {
    if (flyTo && mapRef.current && mapLoaded) {
      mapRef.current.flyTo({ center: [flyTo.lng, flyTo.lat], zoom: 16, duration: 1200 })
    }
  }, [flyTo, mapLoaded])

  const located = occurrences.filter(o => o.lat != null && o.lng != null)

  if (!token) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-canvas gap-2">
        <div className="text-ink text-base font-semibold">Map unavailable</div>
        <div className="text-muted text-sm">Add VITE_MAPBOX_TOKEN to web/.env and restart</div>
      </div>
    )
  }

  return (
    <div className="relative h-full w-full">
      <Map
        ref={mapRef}
        mapboxAccessToken={token}
        initialViewState={{ longitude: -122.2727, latitude: 37.8716, zoom: 13 }}
        style={{ width: '100%', height: '100%' }}
        mapStyle="mapbox://styles/mapbox/dark-v11"
        onLoad={() => setMapLoaded(true)}
        onClick={() => onSelect(null)}
      >
        {located.map((o) => (
          <Marker
            key={o.id}
            longitude={o.lng!}
            latitude={o.lat!}
            onClick={e => { e.originalEvent.stopPropagation(); onSelect(o) }}
          >
            <div
              style={{
                width: selected?.id === o.id ? 20 : 13,
                height: selected?.id === o.id ? 20 : 13,
                borderRadius: '50%',
                backgroundColor: scoreColor(o.score),
                border: `2px solid ${selected?.id === o.id ? '#3b82f6' : 'rgba(14,22,38,0.75)'}`,
                boxShadow: selected?.id === o.id ? '0 0 0 3px rgba(59,130,246,0.4)' : '0 1px 4px rgba(0,0,0,0.6)',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            />
          </Marker>
        ))}

        {selected && selected.lat != null && selected.lng != null && (
          <Popup
            longitude={selected.lng}
            latitude={selected.lat}
            onClose={() => onSelect(null)}
            closeButton
            anchor="bottom"
            offset={16}
          >
            <div className="p-3 min-w-[200px] max-w-[260px]">
              <div
                className="text-[10px] font-bold uppercase tracking-wider mb-1"
                style={{ color: scoreColor(selected.score) }}
              >
                {scoreLabel(selected.score)} · score {selected.score.toFixed(1)}
              </div>
              <div className="font-semibold text-sm capitalize mb-1 text-ink">
                {selected.type.replace(/_/g, ' ')}
              </div>
              {selected.description && (
                <div className="text-xs text-muted mb-2 leading-relaxed">{selected.description}</div>
              )}
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted pt-1 border-t border-line">
                <span>Severity {selected.severity}/5</span>
                {selected.road_name && <span className="text-ink">{selected.road_name}</span>}
              </div>
            </div>
          </Popup>
        )}
      </Map>

      {located.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="bg-panel-2/95 border border-line rounded-card px-6 py-5 max-w-md text-center pointer-events-auto shadow-pop">
            <div className="text-ink font-semibold mb-1">No mapped hazards</div>
            <div className="text-muted text-sm leading-relaxed">
              {locationAvailable
                ? 'No occurrences have coordinates yet. Add one with a location in the Operations DB.'
                : 'This footage has no GPS data, so detected hazards cannot be placed on the map. Review them in Analysis Review, or add located occurrences in the Operations DB.'}
            </div>
          </div>
        </div>
      )}

      <div className="absolute bottom-3 left-3 bg-panel-2/95 border border-line rounded-card px-3 py-2 text-[11px] text-muted space-y-1 shadow-pop">
        <div className="font-semibold text-ink mb-0.5">Severity score</div>
        <div className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded-full" style={{ background: '#e5e7eb' }} /> 0-4 Low</div>
        <div className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded-full" style={{ background: '#f97316' }} /> 4-7 Moderate</div>
        <div className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded-full" style={{ background: '#ef4444' }} /> 7-10 High</div>
      </div>
    </div>
  )
}
