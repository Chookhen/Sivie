import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { Detection } from '../types'

const PRIORITY_COLOR: Record<string, string> = {
  CRITICAL: '#ef4444',
  HIGH:     '#f97316',
  MEDIUM:   '#eab308',
  LOW:      '#6b7280',
}

const PRIORITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']

interface Props { detections: Detection[] }

export default function StatsPanel({ detections }: Props) {
  const byType = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const d of detections) counts[d.type] = (counts[d.type] ?? 0) + 1
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name: name.replace(/_/g, ' '), count }))
  }, [detections])

  const byPriority = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const d of detections) counts[d.priority_label] = (counts[d.priority_label] ?? 0) + 1
    return PRIORITY_ORDER.filter(p => counts[p]).map(name => ({ name, count: counts[name] }))
  }, [detections])

  const critical = detections.filter(d => d.priority_label === 'CRITICAL').length
  const high = detections.filter(d => d.priority_label === 'HIGH').length

  const ttStyle = { background: '#0f172a', border: '1px solid #334155', fontSize: 11, color: '#cbd5e1' }

  return (
    <div className="px-4 py-3 border-b border-slate-700">
      <div className="flex gap-2 mb-3">
        <div className="flex-1 bg-slate-800 rounded-lg p-2 text-center">
          <div className="text-2xl font-bold text-white">{detections.length}</div>
          <div className="text-xs text-slate-400 mt-0.5">Total</div>
        </div>
        <div className="flex-1 bg-red-950/60 rounded-lg p-2 text-center">
          <div className="text-2xl font-bold text-red-400">{critical}</div>
          <div className="text-xs text-red-400/70 mt-0.5">Critical</div>
        </div>
        <div className="flex-1 bg-orange-950/60 rounded-lg p-2 text-center">
          <div className="text-2xl font-bold text-orange-400">{high}</div>
          <div className="text-xs text-orange-400/70 mt-0.5">High</div>
        </div>
      </div>

      <div className="text-xs text-slate-500 uppercase tracking-wider mb-1">By type</div>
      <div className="h-[88px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={byType} margin={{ top: 2, right: 4, bottom: 0, left: -22 }}>
            <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#94a3b8' }} interval={0} />
            <YAxis tick={{ fontSize: 9, fill: '#94a3b8' }} allowDecimals={false} />
            <Tooltip contentStyle={ttStyle} cursor={{ fill: 'rgba(255,255,255,0.05)' }} />
            <Bar dataKey="count" fill="#3b82f6" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="text-xs text-slate-500 uppercase tracking-wider mb-1 mt-2">By priority</div>
      <div className="h-[72px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={byPriority} margin={{ top: 2, right: 4, bottom: 0, left: -22 }}>
            <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#94a3b8' }} />
            <YAxis tick={{ fontSize: 9, fill: '#94a3b8' }} allowDecimals={false} />
            <Tooltip contentStyle={ttStyle} cursor={{ fill: 'rgba(255,255,255,0.05)' }} />
            <Bar dataKey="count" radius={[3, 3, 0, 0]}>
              {byPriority.map(entry => (
                <Cell key={entry.name} fill={PRIORITY_COLOR[entry.name]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
