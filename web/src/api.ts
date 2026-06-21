import {
  DataFile, FileListing, JobStatus, NewOccurrence, Occurrence, OccurrenceDB, ProcessOptions,
} from './types'

// Use 127.0.0.1 (not "localhost") so the browser uses IPv4, matching the
// uvicorn backend bound to 127.0.0.1 (avoids the macOS localhost->::1 mismatch).
export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://127.0.0.1:8000'

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<T>
}

export async function fetchOccurrences(): Promise<OccurrenceDB> {
  return json<OccurrenceDB>(await fetch(`${API_BASE}/api/occurrences`))
}

export async function createOccurrence(payload: NewOccurrence): Promise<Occurrence> {
  return json<Occurrence>(
    await fetch(`${API_BASE}/api/occurrences`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  )
}

export async function deleteOccurrence(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/occurrences/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export async function reseedOccurrences(): Promise<{ reseeded: boolean; count: number }> {
  return json(await fetch(`${API_BASE}/api/reseed`, { method: 'POST' }))
}

// --- Processing: list/upload source files and run the pipeline ------------- //

async function jsonOrDetail<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export async function listFiles(): Promise<FileListing> {
  return json<FileListing>(await fetch(`${API_BASE}/api/files`))
}

export async function uploadFile(file: File, kind: 'video' | 'gps'): Promise<DataFile> {
  const url = `${API_BASE}/api/upload?filename=${encodeURIComponent(file.name)}&kind=${kind}`
  return jsonOrDetail<DataFile>(await fetch(url, { method: 'POST', body: file }))
}

export async function startProcess(opts: ProcessOptions): Promise<JobStatus & { job_id: string }> {
  return jsonOrDetail(
    await fetch(`${API_BASE}/api/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(opts),
    }),
  )
}

export async function getJob(id: string, offset = 0): Promise<JobStatus> {
  return jsonOrDetail<JobStatus>(await fetch(`${API_BASE}/api/process/${id}?offset=${offset}`))
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}

// Severity-score colour scheme (0-10):
//   0-4  -> white   |  4-7 -> orange  |  7-10 -> red
export function scoreColor(score: number): string {
  if (score >= 7) return '#ef4444' // red
  if (score >= 4) return '#f97316' // orange
  return '#e5e7eb' // white-ish (visible on dark map)
}

export function scoreBucket(score: number): 'high' | 'medium' | 'low' {
  if (score >= 7) return 'high'
  if (score >= 4) return 'medium'
  return 'low'
}

export function scoreLabel(score: number): string {
  return { high: 'High', medium: 'Moderate', low: 'Low' }[scoreBucket(score)]
}
