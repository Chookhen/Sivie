import { MapPin, Flame, ListFilter } from 'lucide-react'
import { Detection, IssueType, PriorityLabel } from '../types'
import StatsPanel from './StatsPanel'

const PRIORITY_COLOR: Record<string, string> = {
  CRITICAL: '#ef4444',
  HIGH:     '#f97316',
  MEDIUM:   '#eab308',
  LOW:      '#6b7280',
}

const PRIORITY_LABELS: PriorityLabel[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const ISSUE_TYPES: IssueType[] = ['pothole', 'crack', 'obscured_sign', 'faded_marking', 'debris', 'other']

interface Props {
  detections: Detection[]
  allDetections: Detection[]
  selected: Detection | null
  filterPriority: PriorityLabel | 'ALL'
  filterType: IssueType | 'ALL'
  onFilterPriority: (v: PriorityLabel | 'ALL') => void
  onFilterType: (v: IssueType | 'ALL') => void
  onSelect: (d: Detection) => void
  showHeatmap: boolean
  onToggleHeatmap: () => void
}

export default function Sidebar({
  detections, allDetections, selected,
  filterPriority, filterType,
  onFilterPriority, onFilterType,
  onSelect, showHeatmap, onToggleHeatmap,
}: Props) {
  return (
    <div className="w-80 shrink-0 bg-slate-900 border-r border-slate-700 flex flex-col h-full text-slate-100">
      <div className="px-4 py-3 border-b border-slate-700 flex items-center gap-2">
        <MapPin size={18} className="text-blue-400 shrink-0" />
        <div>
          <h1 className="text-sm font-bold text-white leading-tight">Road Hazard Monitor</h1>
          <p className="text-xs text-slate-500">{allDetections.length} detections · Berkeley</p>
        </div>
      </div>

      <StatsPanel detections={allDetections} />

      <div className="px-4 py-3 border-b border-slate-700 space-y-2">
        <div className="flex items-center gap-2">
          <ListFilter size={13} className="text-slate-500" />
          <span className="text-xs text-slate-500 uppercase tracking-wider">Filters</span>
          <button
            onClick={onToggleHeatmap}
            className={`ml-auto flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
              showHeatmap
                ? 'bg-orange-500 text-white'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            <Flame size={12} />
            Heatmap
          </button>
        </div>

        <select
          className="w-full bg-slate-800 text-slate-200 text-xs rounded-md px-3 py-2 border border-slate-700 focus:outline-none focus:border-blue-500"
          value={filterPriority}
          onChange={e => onFilterPriority(e.target.value as PriorityLabel | 'ALL')}
        >
          <option value="ALL">All priorities</option>
          {PRIORITY_LABELS.map(p => <option key={p} value={p}>{p}</option>)}
        </select>

        <select
          className="w-full bg-slate-800 text-slate-200 text-xs rounded-md px-3 py-2 border border-slate-700 focus:outline-none focus:border-blue-500"
          value={filterType}
          onChange={e => onFilterType(e.target.value as IssueType | 'ALL')}
        >
          <option value="ALL">All types</option>
          {ISSUE_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
        </select>
      </div>

      <div className="px-4 py-2 border-b border-slate-700 flex items-center justify-between">
        <span className="text-xs text-slate-500 uppercase tracking-wider">Work orders</span>
        <span className="text-xs text-slate-600">{detections.length} shown</span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {detections.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-slate-600 text-sm gap-1">
            <span>No detections match</span>
            <span className="text-xs">Adjust filters above</span>
          </div>
        ) : (
          detections.map((d, i) => {
            const isSelected = selected === d
            return (
              <button
                key={i}
                onClick={() => onSelect(d)}
                className={`w-full text-left px-4 py-3 border-b border-slate-800 transition-colors ${
                  isSelected ? 'bg-slate-800' : 'hover:bg-slate-800/60'
                }`}
                style={isSelected ? { borderLeft: `3px solid ${PRIORITY_COLOR[d.priority_label]}` } : { borderLeft: '3px solid transparent' }}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <span
                    className="text-xs font-bold uppercase tracking-wider"
                    style={{ color: PRIORITY_COLOR[d.priority_label] }}
                  >
                    {d.priority_label}
                  </span>
                  <span className="text-xs text-slate-500 tabular-nums">{d.priority.toFixed(1)}</span>
                </div>
                <div className="text-sm font-medium text-slate-200 capitalize">
                  {d.type.replace(/_/g, ' ')}
                </div>
                <div className="text-xs text-slate-500 truncate mt-0.5">{d.description}</div>
                <div className="text-xs text-slate-600 mt-1 capitalize">
                  {d.road_context} · {d.frame}
                </div>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}
