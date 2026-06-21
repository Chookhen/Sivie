import { useRef, useEffect, useMemo, useState } from 'react'
import Map, { Marker, Source, Layer, Popup } from 'react-map-gl'
import type { MapRef } from 'react-map-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { Detection } from '../types'

const PRIORITY_COLOR: Record<string, string> = {
  CRITICAL: '#ef4444',
  HIGH:     '#f97316',
  MEDIUM:   '#eab308',
  LOW:      '#6b7280',
}

interface Props {
  detections: Detection[]
  selected: Detection | null
  flyTo: { lat: number; lng: number; ts: number } | null
  showHeatmap: boolean
  onSelect: (d: Detection | null) => void
}

export default function MapView({ detections, selected, flyTo, showHeatmap, onSelect }: Props) {
  const mapRef = useRef<MapRef | null>(null)
  const [mapLoaded, setMapLoaded] = useState(false)
  const token = import.meta.env.VITE_MAPBOX_TOKEN as string | undefined

  useEffect(() => {
    if (flyTo && mapRef.current && mapLoaded) {
      mapRef.current.flyTo({ center: [flyTo.lng, flyTo.lat], zoom: 16, duration: 1200 })
    }
  }, [flyTo, mapLoaded])

  const geojson = useMemo(() => ({
    type: 'FeatureCollection' as const,
    features: detections.map(d => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [d.lng!, d.lat!] },
      properties: { priority: d.priority },
    })),
  }), [detections])

  if (!token) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-slate-800 gap-3">
        <div className="text-slate-300 text-lg font-semibold">Map unavailable</div>
        <div className="text-slate-500 text-sm">Add VITE_MAPBOX_TOKEN to web/.env and restart</div>
      </div>
    )
  }

  return (
    <Map
      ref={mapRef}
      mapboxAccessToken={token}
      initialViewState={{ longitude: -122.2727, latitude: 37.8716, zoom: 13 }}
      style={{ width: '100%', height: '100%' }}
      mapStyle="mapbox://styles/mapbox/dark-v11"
      onLoad={() => setMapLoaded(true)}
      onClick={() => onSelect(null)}
    >
      {showHeatmap && (
        <Source id="heatmap-src" type="geojson" data={geojson}>
          <Layer
            id="heatmap"
            type="heatmap"
            paint={{
              'heatmap-weight': ['interpolate', ['linear'], ['get', 'priority'], 0, 0, 25, 1],
              'heatmap-intensity': 1.2,
              'heatmap-color': [
                'interpolate', ['linear'], ['heatmap-density'],
                0,   'rgba(0,0,255,0)',
                0.3, 'rgba(0,200,255,0.5)',
                0.6, 'rgba(255,165,0,0.8)',
                1,   'rgba(239,68,68,1)',
              ],
              'heatmap-radius': 35,
              'heatmap-opacity': 0.75,
            }}
          />
        </Source>
      )}

      {detections.map((d, i) => (
        <Marker
          key={i}
          longitude={d.lng!}
          latitude={d.lat!}
          onClick={e => { e.originalEvent.stopPropagation(); onSelect(d) }}
        >
          <div
            style={{
              width: selected === d ? 18 : 12,
              height: selected === d ? 18 : 12,
              borderRadius: '50%',
              backgroundColor: PRIORITY_COLOR[d.priority_label],
              border: `2px solid ${selected === d ? '#fff' : 'rgba(255,255,255,0.6)'}`,
              boxShadow: selected === d ? `0 0 0 3px ${PRIORITY_COLOR[d.priority_label]}55` : '0 1px 4px rgba(0,0,0,0.5)',
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
          />
        </Marker>
      ))}

      {selected && selected.lat !== null && selected.lng !== null && (
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
              className="text-xs font-bold uppercase tracking-wider mb-1"
              style={{ color: PRIORITY_COLOR[selected.priority_label] }}
            >
              {selected.priority_label} · {selected.priority.toFixed(1)}
            </div>
            <div className="font-semibold text-sm capitalize mb-1 text-slate-100">
              {selected.type.replace(/_/g, ' ')}
            </div>
            <div className="text-xs text-slate-400 mb-2 leading-relaxed">{selected.description}</div>
            <div className="flex gap-3 text-xs text-slate-400">
              <span>Severity {selected.severity}/5</span>
              <span>Conf {Math.round(selected.confidence * 100)}%</span>
              <span className="capitalize">{selected.road_context}</span>
            </div>
            <div className="text-xs text-slate-500 mt-1">{selected.frame}</div>
          </div>
        </Popup>
      )}
    </Map>
  )
}
