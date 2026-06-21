import { useEffect, useState, useCallback } from 'react'
import { Trash2, Plus, RefreshCw, Database, MapPin, AlertCircle } from 'lucide-react'
import { Occurrence, IssueType, NewOccurrence } from '../types'
import {
  fetchOccurrences, createOccurrence, deleteOccurrence, reseedOccurrences,
  scoreColor, scoreLabel, API_BASE,
} from '../api'

const ISSUE_TYPES: IssueType[] = [
  'pothole', 'crack', 'obscured_sign', 'faded_marking', 'debris', 'other',
]

const EMPTY_FORM: NewOccurrence = {
  type: 'pothole',
  description: '',
  severity: 3,
  score: null,
  lat: null,
  lng: null,
  road_name: '',
}

export default function DatabasePage() {
  const [occurrences, setOccurrences] = useState<Occurrence[]>([])
  const [meta, setMeta] = useState<{ backend?: string; location_available: boolean; source_video?: string | null; located_count: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<NewOccurrence>(EMPTY_FORM)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const db = await fetchOccurrences()
      setOccurrences(db.occurrences)
      setMeta({ backend: db.backend, location_available: db.location_available, source_video: db.source_video, located_count: db.located_count })
      setError(null)
    } catch {
      setError(`Cannot reach the backend at ${API_BASE}. Start it with: uvicorn server.app:app --port 8000`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const payload: NewOccurrence = {
        ...form,
        road_name: form.road_name || null,
        description: form.description || '',
        lat: form.lat === null || Number.isNaN(form.lat) ? null : Number(form.lat),
        lng: form.lng === null || Number.isNaN(form.lng) ? null : Number(form.lng),
        score: form.score == null ? null : Number(form.score),
      }
      await createOccurrence(payload)
      setForm(EMPTY_FORM)
      setShowForm(false)
      await load()
    } catch {
      setError('Failed to add occurrence.')
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(id: string) {
    setBusy(true)
    try {
      await deleteOccurrence(id)
      setOccurrences(prev => prev.filter(o => o.id !== id))
    } catch {
      setError('Failed to delete occurrence.')
    } finally {
      setBusy(false)
    }
  }

  async function handleReseed() {
    if (!confirm('Rebuild the database from the latest detection output? This drops manual edits.')) return
    setBusy(true)
    try {
      await reseedOccurrences()
      await load()
    } catch {
      setError('Failed to reseed.')
    } finally {
      setBusy(false)
    }
  }

  const counts = {
    total: occurrences.length,
    high: occurrences.filter(o => o.score >= 7).length,
    medium: occurrences.filter(o => o.score >= 4 && o.score < 7).length,
    low: occurrences.filter(o => o.score < 4).length,
  }

  return (
    <div className="flex-1 min-h-0 overflow-auto bg-canvas text-ink">
      <div className="max-w-6xl mx-auto p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="grid place-items-center w-9 h-9 rounded-lg bg-primary/15 border border-primary/30">
            <Database size={18} className="text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-ink flex items-center gap-2">
              Operations Database
              {meta?.backend && (
                <span className={`badge ${meta.backend === 'supabase' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-panel-3 text-muted'}`}>
                  {meta.backend === 'supabase' ? 'Supabase' : 'Local JSON'}
                </span>
              )}
            </h1>
            <p className="text-xs text-muted">
              {meta?.source_video ? `Source: ${meta.source_video}` : 'Hazard occurrence registry'}
              {meta && !meta.location_available && ' · no GPS in source footage (markers hidden on map)'}
            </p>
          </div>
          <div className="ml-auto flex gap-2">
            <button onClick={() => setShowForm(v => !v)} className="btn-primary">
              <Plus size={13} /> Add occurrence
            </button>
            <button onClick={handleReseed} disabled={busy} className="btn-ghost">
              <RefreshCw size={13} /> Reseed
            </button>
          </div>
        </div>

        {error && (
          <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/40 rounded-card px-4 py-3 text-sm text-red-300">
            <AlertCircle size={16} className="shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Total', value: counts.total, color: '#e8edf6' },
            { label: 'High (7-10)', value: counts.high, color: '#ef4444' },
            { label: 'Moderate (4-7)', value: counts.medium, color: '#f97316' },
            { label: 'Low (0-4)', value: counts.low, color: '#cbd5e1' },
          ].map(s => (
            <div key={s.label} className="card px-4 py-3">
              <div className="text-2xl font-bold tabular-nums" style={{ color: s.color }}>{s.value}</div>
              <div className="text-[11px] uppercase tracking-wide text-faint mt-0.5">{s.label}</div>
            </div>
          ))}
        </div>

        {/* Add form */}
        {showForm && (
          <form onSubmit={handleAdd} className="card p-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
            <label className="field-label">
              Type
              <select
                value={form.type}
                onChange={e => setForm({ ...form, type: e.target.value as IssueType })}
                className="select capitalize"
              >
                {ISSUE_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
              </select>
            </label>
            <label className="field-label">
              Severity (1-5)
              <input type="number" min={1} max={5} value={form.severity ?? 3}
                onChange={e => setForm({ ...form, severity: Number(e.target.value) })}
                className="input" />
            </label>
            <label className="field-label">
              Score (0-10, optional)
              <input type="number" min={0} max={10} step={0.1} value={form.score ?? ''}
                placeholder="auto from severity"
                onChange={e => setForm({ ...form, score: e.target.value === '' ? null : Number(e.target.value) })}
                className="input" />
            </label>
            <label className="field-label">
              Latitude (optional)
              <input type="number" step="any" value={form.lat ?? ''}
                onChange={e => setForm({ ...form, lat: e.target.value === '' ? null : Number(e.target.value) })}
                className="input" />
            </label>
            <label className="field-label">
              Longitude (optional)
              <input type="number" step="any" value={form.lng ?? ''}
                onChange={e => setForm({ ...form, lng: e.target.value === '' ? null : Number(e.target.value) })}
                className="input" />
            </label>
            <label className="field-label">
              Road name (optional)
              <input type="text" value={form.road_name ?? ''}
                onChange={e => setForm({ ...form, road_name: e.target.value })}
                className="input" />
            </label>
            <label className="field-label col-span-2 sm:col-span-3">
              Description (optional)
              <input type="text" value={form.description ?? ''}
                onChange={e => setForm({ ...form, description: e.target.value })}
                className="input" />
            </label>
            <div className="col-span-2 sm:col-span-3 flex gap-2 pt-1">
              <button type="submit" disabled={busy} className="btn-primary px-4">
                Save occurrence
              </button>
              <button type="button" onClick={() => { setShowForm(false); setForm(EMPTY_FORM) }} className="btn-ghost px-4">
                Cancel
              </button>
            </div>
          </form>
        )}

        {/* Table */}
        {loading ? (
          <div className="text-muted text-sm py-10 text-center animate-pulse">Loading database…</div>
        ) : occurrences.length === 0 ? (
          <div className="text-muted text-sm py-10 text-center card">No occurrences in the database.</div>
        ) : (
          <div className="overflow-x-auto card">
            <table className="w-full text-sm">
              <thead className="bg-panel-2 text-faint text-xs uppercase tracking-wider">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">Severity</th>
                  <th className="text-left px-3 py-2 font-medium">Type</th>
                  <th className="text-left px-3 py-2 font-medium">Road</th>
                  <th className="text-left px-3 py-2 font-medium">Location</th>
                  <th className="text-left px-3 py-2 font-medium">Source</th>
                  <th className="text-left px-3 py-2 font-medium">Seen</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line-soft">
                {occurrences.map(o => (
                  <tr key={o.id} className="hover:bg-panel-2/50 transition-colors">
                    <td className="px-3 py-2.5">
                      <span className="inline-flex items-center gap-2">
                        <span className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                          style={{ background: scoreColor(o.score), border: '1px solid rgba(148,163,184,0.35)' }} />
                        <span className="tabular-nums font-semibold" style={{ color: scoreColor(o.score) }}>
                          {o.score.toFixed(1)}
                        </span>
                        <span className="text-faint text-xs">{scoreLabel(o.score)}</span>
                      </span>
                    </td>
                    <td className="px-3 py-2.5 capitalize text-ink">{o.type.replace(/_/g, ' ')}</td>
                    <td className="px-3 py-2.5 text-muted">{o.road_name ?? '—'}</td>
                    <td className="px-3 py-2.5 text-muted">
                      {o.lat != null && o.lng != null ? (
                        <span className="inline-flex items-center gap-1 tabular-nums">
                          <MapPin size={11} className="text-faint" /> {o.lat.toFixed(5)}, {o.lng.toFixed(5)}
                        </span>
                      ) : <span className="text-faint">—</span>}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`badge ${o.source === 'manual' ? 'bg-primary/15 text-primary' : 'bg-panel-3 text-muted'}`}>
                        {o.source}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-muted tabular-nums">{o.times_seen ?? 1}×</td>
                    <td className="px-3 py-2.5 text-right">
                      <button onClick={() => handleDelete(o.id)} disabled={busy}
                        className="text-faint hover:text-red-400 transition-colors disabled:opacity-40 p-1 rounded hover:bg-red-500/10"
                        title="Remove from database">
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
