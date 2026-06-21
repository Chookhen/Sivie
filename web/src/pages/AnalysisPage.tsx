import { useState, useMemo } from 'react'
import { ImageOff, MapPin, AlertCircle, X, Brain } from 'lucide-react'
import { Detection, IssueType, PriorityLabel } from '../types'

const PRIORITY_COLOR: Record<string, string> = {
  CRITICAL: '#ef4444',
  HIGH:     '#f97316',
  MEDIUM:   '#eab308',
  LOW:      '#6b7280',
}

const PRIORITY_LABELS: PriorityLabel[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const ISSUE_TYPES: IssueType[] = ['pothole', 'crack', 'obscured_sign', 'faded_marking', 'debris', 'other']

interface FrameGroup {
  frame: string
  image_url: string | null | undefined
  detections: Detection[]
  max_priority: number
  max_priority_label: PriorityLabel
}

function FrameImage({
  src, alt, detections, activeIdx, onBoxClick, fill = true,
}: {
  src?: string | null
  alt: string
  detections: Detection[]
  activeIdx?: number | null
  onBoxClick?: (idx: number) => void
  fill?: boolean
}) {
  const [imgErr, setImgErr] = useState(false)

  const wrapCls = fill ? 'relative w-full h-full' : 'relative w-full'
  const imgCls  = fill ? 'w-full h-full object-cover bg-slate-700' : 'w-full h-auto block bg-slate-900'

  if (!src || imgErr) {
    return (
      <div className={`${wrapCls} flex flex-col items-center justify-center gap-1.5 text-slate-600 bg-slate-700`}>
        <ImageOff size={28} />
        <span className="text-xs">No image</span>
      </div>
    )
  }

  return (
    <div className={wrapCls}>
      <img src={src} alt={alt} className={imgCls} onError={() => setImgErr(true)} />
      {detections.map((d, i) => {
        if (!d.box_2d) return null
        const [ymin, xmin, ymax, xmax] = d.box_2d
        const color = PRIORITY_COLOR[d.priority_label]
        const isActive = activeIdx === i
        const score = (d.final_priority ?? d.priority).toFixed(1)
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left:   `${xmin / 10}%`,
              top:    `${ymin / 10}%`,
              width:  `${(xmax - xmin) / 10}%`,
              height: `${(ymax - ymin) / 10}%`,
              border: `${isActive ? 2.5 : 1.5}px solid ${color}`,
              borderRadius: 2,
              boxShadow: isActive ? `0 0 0 1px ${color}55, 0 0 8px ${color}77` : undefined,
              cursor: onBoxClick ? 'pointer' : undefined,
              transition: 'border-width 0.1s, box-shadow 0.15s',
            }}
            onClick={onBoxClick ? (e) => { e.stopPropagation(); onBoxClick(i) } : undefined}
          >
            <span
              style={{
                position: 'absolute',
                bottom: '100%',
                left: -1,
                background: color,
                color: '#fff',
                fontSize: 9,
                lineHeight: '14px',
                padding: '0 3px',
                borderRadius: '2px 2px 0 0',
                whiteSpace: 'nowrap',
                fontWeight: 700,
                pointerEvents: 'none',
                userSelect: 'none',
              } as React.CSSProperties}
            >
              {d.type.replace(/_/g, ' ')} {score}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function FrameCard({ group, onClick }: { group: FrameGroup; onClick: () => void }) {
  const d0 = group.detections[0]
  const color = PRIORITY_COLOR[group.max_priority_label]

  return (
    <button
      onClick={onClick}
      className="bg-slate-800 rounded-lg overflow-hidden border border-slate-700 hover:border-slate-500 transition-all text-left w-full hover:shadow-lg hover:shadow-black/30"
      style={{ borderLeftColor: color, borderLeftWidth: 3 }}
    >
      <div className="relative h-44 bg-slate-700 overflow-hidden">
        <FrameImage
          src={group.image_url}
          alt={group.frame}
          detections={group.detections}
        />
        <div
          className="absolute top-2 right-2 z-10 text-xs font-bold px-2 py-0.5 rounded backdrop-blur-sm"
          style={{ background: `${color}33`, color, border: `1px solid ${color}55` }}
        >
          {group.max_priority_label}
        </div>
        {group.detections.length > 1 && (
          <div className="absolute bottom-2 left-2 z-10 text-xs px-2 py-0.5 rounded bg-black/60 text-slate-300">
            {group.detections.length} issues
          </div>
        )}
      </div>

      <div className="p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-mono text-slate-400 truncate">{group.frame}</span>
          <span className="text-xs tabular-nums shrink-0 ml-2" style={{ color }}>
            {group.max_priority.toFixed(1)}
          </span>
        </div>

        <div className="space-y-1.5 mb-2">
          {group.detections.slice(0, 3).map((d, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: PRIORITY_COLOR[d.priority_label] }} />
              <span className="capitalize text-slate-200">{d.type.replace(/_/g, ' ')}</span>
              <span className="text-slate-500 ml-auto">sev {d.severity} · {Math.round(d.confidence * 100)}%</span>
            </div>
          ))}
          {group.detections.length > 3 && (
            <div className="text-xs text-slate-600">+{group.detections.length - 3} more</div>
          )}
        </div>

        {d0.lat != null && (
          <div className="flex items-center gap-1 text-xs text-slate-500 mt-1.5">
            <MapPin size={10} className="shrink-0" />
            <span className="truncate">
              {d0.lat.toFixed(4)}, {d0.lng?.toFixed(4)}
              {d0.road_name && <span className="text-slate-400"> · {d0.road_name}</span>}
            </span>
          </div>
        )}

        {d0.justification && (
          <p className="text-xs text-slate-500 mt-2 line-clamp-2 italic">"{d0.justification}"</p>
        )}
      </div>
    </button>
  )
}

function DetectionDetail({ d, active = false }: { d: Detection; active?: boolean }) {
  const color = PRIORITY_COLOR[d.priority_label]
  return (
    <div
      className="border rounded-lg p-3 space-y-2 transition-colors"
      style={active
        ? { borderColor: `${color}77`, background: `${color}11` }
        : { borderColor: '#334155' }}
    >
      <div className="flex items-center gap-2 flex-wrap">
        <span
          className="text-xs font-bold px-2 py-0.5 rounded"
          style={{ color, background: `${color}22`, border: `1px solid ${color}44` }}
        >
          {d.priority_label}
        </span>
        <span className="font-medium text-sm capitalize text-slate-100">
          {d.type.replace(/_/g, ' ')}
        </span>
        <span className="text-xs text-slate-500 ml-auto">score {d.priority.toFixed(2)}</span>
      </div>

      {d.description && (
        <p className="text-xs text-slate-400">{d.description}</p>
      )}

      <div className="flex flex-wrap gap-3 text-xs text-slate-500">
        <span>Severity {d.severity}/5</span>
        <span>Confidence {Math.round(d.confidence * 100)}%</span>
        <span className="capitalize">{d.road_context}</span>
      </div>

      {d.lat != null && (
        <div className="flex items-start gap-1 text-xs text-slate-500">
          <MapPin size={10} className="mt-0.5 shrink-0" />
          <span>
            {d.lat.toFixed(5)}, {d.lng?.toFixed(5)}
            {d.road_name && <span className="text-slate-400"> · {d.road_name}</span>}
            {d.road_class && <span className="text-slate-600"> ({d.road_class})</span>}
          </span>
        </div>
      )}

      {d.nearby_pois && d.nearby_pois.length > 0 && (
        <div className="text-xs text-slate-500">
          Nearby: {d.nearby_pois.map(p => `${p.name ?? p.category} (${p.distance_m}m)`).join(' · ')}
        </div>
      )}

      {(d.priority_multiplier != null || d.final_priority != null) && (
        <div className="text-xs text-slate-400 flex gap-3 flex-wrap">
          {d.priority_multiplier != null && <span>AI multiplier ×{d.priority_multiplier}</span>}
          {d.final_priority != null && <span>Final priority {d.final_priority.toFixed(2)}</span>}
        </div>
      )}

      {d.justification && (
        <div className="flex gap-2 text-xs bg-slate-900/60 rounded p-2.5">
          <Brain size={12} className="text-blue-400 shrink-0 mt-0.5" />
          <span className="text-slate-300 italic">"{d.justification}"</span>
        </div>
      )}
    </div>
  )
}

function DetailModal({ group, onClose }: { group: FrameGroup; onClose: () => void }) {
  const color = PRIORITY_COLOR[group.max_priority_label]
  const [activeBox, setActiveBox] = useState<number | null>(null)

  const toggleBox = (i: number) => setActiveBox(prev => prev === i ? null : i)

  return (
    <div
      className="fixed inset-0 bg-black/75 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-slate-800 rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 sticky top-0 bg-slate-800 rounded-t-xl z-10">
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm text-slate-300">{group.frame}</span>
            <span
              className="text-xs font-bold px-2 py-0.5 rounded"
              style={{ color, background: `${color}22`, border: `1px solid ${color}44` }}
            >
              {group.max_priority_label} · {group.max_priority.toFixed(1)}
            </span>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-700">
            <X size={18} />
          </button>
        </div>

        <div className="bg-slate-900 overflow-hidden">
          <FrameImage
            src={group.image_url}
            alt={group.frame}
            detections={group.detections}
            activeIdx={activeBox}
            onBoxClick={toggleBox}
            fill={false}
          />
        </div>

        <div className="p-4 space-y-3">
          <div className="text-xs text-slate-500 uppercase tracking-wider">
            {group.detections.length} Detection{group.detections.length !== 1 ? 's' : ''}
            {group.detections.some(d => d.box_2d) && (
              <span className="ml-2 normal-case text-slate-600">· click a row to highlight its box</span>
            )}
          </div>
          {group.detections.map((d, i) => (
            <div
              key={i}
              onClick={() => d.box_2d != null && toggleBox(i)}
              className={d.box_2d != null ? 'cursor-pointer' : ''}
            >
              <DetectionDetail d={d} active={activeBox === i} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

interface Props {
  detections: Detection[]
}

export default function AnalysisPage({ detections }: Props) {
  const [filterPriority, setFilterPriority] = useState<PriorityLabel | 'ALL'>('ALL')
  const [filterType, setFilterType] = useState<IssueType | 'ALL'>('ALL')
  const [selected, setSelected] = useState<FrameGroup | null>(null)

  const frameGroups = useMemo((): FrameGroup[] => {
    const map = new Map<string, Detection[]>()
    for (const d of detections) {
      if (!map.has(d.frame)) map.set(d.frame, [])
      map.get(d.frame)!.push(d)
    }
    return Array.from(map.entries())
      .map(([frame, dets]) => {
        const sorted = [...dets].sort((a, b) => b.priority - a.priority)
        return {
          frame,
          image_url: dets.find(d => d.image_url)?.image_url,
          detections: sorted,
          max_priority: sorted[0].priority,
          max_priority_label: sorted[0].priority_label,
        }
      })
      .sort((a, b) => b.max_priority - a.max_priority)
  }, [detections])

  const filtered = useMemo(() =>
    frameGroups.filter(g =>
      (filterPriority === 'ALL' || g.detections.some(d => d.priority_label === filterPriority)) &&
      (filterType === 'ALL' || g.detections.some(d => d.type === filterType)),
    ), [frameGroups, filterPriority, filterType])

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-slate-900">
      <div className="px-6 py-2.5 border-b border-slate-700 flex items-center gap-3 shrink-0 flex-wrap">
        <span className="text-xs text-slate-500">
          {filtered.length} frame{filtered.length !== 1 ? 's' : ''} · {detections.length} total detections
        </span>
        <div className="flex gap-2 ml-auto">
          <select
            className="bg-slate-800 text-slate-200 text-xs rounded-md px-3 py-1.5 border border-slate-700 focus:outline-none focus:border-blue-500"
            value={filterPriority}
            onChange={e => setFilterPriority(e.target.value as PriorityLabel | 'ALL')}
          >
            <option value="ALL">All priorities</option>
            {PRIORITY_LABELS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <select
            className="bg-slate-800 text-slate-200 text-xs rounded-md px-3 py-1.5 border border-slate-700 focus:outline-none focus:border-blue-500"
            value={filterType}
            onChange={e => setFilterType(e.target.value as IssueType | 'ALL')}
          >
            <option value="ALL">All types</option>
            {ISSUE_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
          </select>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {detections.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-slate-600 gap-2">
            <AlertCircle size={32} />
            <p className="text-sm">No detections loaded</p>
            <p className="text-xs">Run the pipeline with --save-frames-dir to populate this page</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex items-center justify-center h-64 text-slate-600 text-sm">
            No frames match the current filters
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filtered.map(group => (
              <FrameCard key={group.frame} group={group} onClick={() => setSelected(group)} />
            ))}
          </div>
        )}
      </div>

      {selected && <DetailModal group={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
