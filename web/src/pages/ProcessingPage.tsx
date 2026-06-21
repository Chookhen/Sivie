import { useEffect, useRef, useState } from 'react'
import {
  FileVideo, MapPin, UploadCloud, Play, RefreshCw, Loader2, CheckCircle2,
  XCircle, Terminal, FolderOpen, Settings2, Ban,
} from 'lucide-react'
import { DataFile, FileListing, JobStatus, ProcessOptions } from '../types'
import { listFiles, uploadFile, startProcess, getJob, formatBytes } from '../api'
import { Page } from '../components/NavBar'

interface Props {
  onNavigate: (page: Page) => void
  onProcessed: () => void
}

const POLL_MS = 1200

export default function ProcessingPage({ onNavigate, onProcessed }: Props) {
  const [listing, setListing] = useState<FileListing | null>(null)
  const [listError, setListError] = useState<string | null>(null)

  const [video, setVideo] = useState<string | null>(null)
  const [gps, setGps] = useState<string | null>(null)

  const [timeOffset, setTimeOffset] = useState('-3')
  const [fps, setFps] = useState('1')
  const [maxFrames, setMaxFrames] = useState('')
  const [detector, setDetector] = useState<'yolo' | 'gemini'>('yolo')
  const [yoloConf, setYoloConf] = useState('0.25')
  const [minConf, setMinConf] = useState('0')
  const [dedupe, setDedupe] = useState(true)
  const [enrich, setEnrich] = useState(true)
  const [aiPriority, setAiPriority] = useState(false)
  const [mock, setMock] = useState(false)

  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [job, setJob] = useState<JobStatus | null>(null)
  const [running, setRunning] = useState(false)
  const [logLines, setLogLines] = useState<string[]>([])

  const offsetRef = useRef(0)
  const timerRef = useRef<number | null>(null)
  const logRef = useRef<HTMLDivElement | null>(null)

  async function load() {
    setListError(null)
    try {
      const data = await listFiles()
      setListing(data)
      setVideo(prev => prev ?? data.videos[0]?.path ?? null)
    } catch (e) {
      setListError((e as Error).message)
    }
  }

  useEffect(() => { load() }, [])

  useEffect(() => () => stopPolling(), [])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logLines])

  function stopPolling() {
    if (timerRef.current != null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  function startPolling(id: string) {
    stopPolling()
    timerRef.current = window.setInterval(async () => {
      try {
        const s = await getJob(id, offsetRef.current)
        if (s.log.length) {
          setLogLines(prev => [...prev, ...s.log])
          offsetRef.current = s.next_offset
        }
        setJob(s)
        if (s.status !== 'running') {
          stopPolling()
          setRunning(false)
          if (s.status === 'done') onProcessed()
        }
      } catch {
        /* transient poll error: keep trying */
      }
    }, POLL_MS)
  }

  async function handleUpload(files: FileList | null, kind: 'video' | 'gps') {
    if (!files || files.length === 0) return
    setUploading(true)
    setError(null)
    try {
      let last: DataFile | null = null
      for (const f of Array.from(files)) {
        last = await uploadFile(f, kind)
      }
      await load()
      if (last) {
        if (kind === 'video') setVideo(last.path)
        else setGps(last.path)
      }
    } catch (e) {
      setError(`Upload failed: ${(e as Error).message}`)
    } finally {
      setUploading(false)
    }
  }

  async function run() {
    if (!video) return
    setError(null)
    setLogLines([])
    offsetRef.current = 0
    const opts: ProcessOptions = {
      video,
      gps: gps || null,
      time_offset: Number(timeOffset) || 0,
      fps: Number(fps) || 1,
      max_frames: maxFrames === '' ? null : Number(maxFrames),
      detector,
      yolo_conf: Number(yoloConf) || 0.25,
      min_confidence: Number(minConf) || 0,
      mock,
      dedupe,
      enrich,
      ai_priority: aiPriority,
    }
    try {
      const snap = await startProcess(opts)
      setJob(snap)
      setLogLines(snap.log)
      offsetRef.current = snap.next_offset
      setRunning(true)
      startPolling(snap.job_id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const videos = listing?.videos ?? []
  const tracks = listing?.gps ?? []

  return (
    <div className="flex-1 min-h-0 overflow-auto bg-canvas text-ink">
      <div className="max-w-6xl mx-auto p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="grid place-items-center w-9 h-9 rounded-lg bg-primary/15 border border-primary/30">
            <Settings2 size={18} className="text-primary" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-ink">Processing</h1>
            <p className="text-xs text-muted">
              Select footage from the connected directory (or upload), then run the detection pipeline.
            </p>
          </div>
          <button onClick={load} className="btn-ghost ml-auto" disabled={running}>
            <RefreshCw size={13} /> Refresh files
          </button>
        </div>

        {error && (
          <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/40 rounded-card px-4 py-3 text-sm text-red-300">
            <XCircle size={16} className="shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
        {listError && (
          <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/40 rounded-card px-4 py-3 text-sm text-red-300">
            <XCircle size={16} className="shrink-0 mt-0.5" />
            <span>Backend offline — start it with: uvicorn server.app:app --port 8000</span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* File browser */}
          <div className="card p-4 space-y-4">
            <FileSection
              title="Video footage"
              icon={<FileVideo size={14} className="text-primary" />}
              files={videos}
              selected={video}
              onSelect={setVideo}
              emptyHint="No videos found in test_images/, samples/, or data/uploads/"
              accept="video/*,.mov,.mp4,.avi,.mkv,.m4v,.webm"
              kind="video"
              onUpload={handleUpload}
              uploading={uploading}
              disabled={running}
            />
            <div className="border-t border-line-soft" />
            <FileSection
              title="GPS track (optional)"
              icon={<MapPin size={14} className="text-primary" />}
              files={tracks}
              selected={gps}
              onSelect={setGps}
              allowNone
              emptyHint="No .gpx / .csv tracks found. Run without GPS for a no-map analysis."
              accept=".gpx,.csv"
              kind="gps"
              onUpload={handleUpload}
              uploading={uploading}
              disabled={running}
            />
          </div>

          {/* Options + Run */}
          <div className="card p-4 space-y-4">
            <div className="text-[11px] uppercase tracking-wide text-faint font-semibold flex items-center gap-1.5">
              <Settings2 size={13} /> Pipeline options
            </div>

            <div className="grid grid-cols-2 gap-3">
              <label className="field-label">
                GPS time offset (s)
                <input className="input" value={timeOffset} onChange={e => setTimeOffset(e.target.value)} disabled={running} />
              </label>
              <label className="field-label">
                Frames / sec
                <input className="input" value={fps} onChange={e => setFps(e.target.value)} disabled={running} />
              </label>
              <label className="field-label">
                Max frames (blank = all)
                <input className="input" value={maxFrames} placeholder="all" onChange={e => setMaxFrames(e.target.value)} disabled={running} />
              </label>
              <label className="field-label">
                Detector
                <select className="select" value={detector} onChange={e => setDetector(e.target.value as 'yolo' | 'gemini')} disabled={running}>
                  <option value="yolo">YOLO (local)</option>
                  <option value="gemini">Gemini (VLM)</option>
                </select>
              </label>
              <label className="field-label">
                YOLO confidence
                <input className="input" value={yoloConf} onChange={e => setYoloConf(e.target.value)} disabled={running} />
              </label>
              <label className="field-label">
                Min confidence
                <input className="input" value={minConf} onChange={e => setMinConf(e.target.value)} disabled={running} />
              </label>
            </div>

            <div className="flex flex-wrap gap-x-4 gap-y-2 pt-1">
              <Toggle label="Dedupe hazards" checked={dedupe} onChange={setDedupe} disabled={running} />
              <Toggle label="OSM enrich (road names)" checked={enrich} onChange={setEnrich} disabled={running} />
              <Toggle label="AI priority (Gemini)" checked={aiPriority} onChange={setAiPriority} disabled={running} />
              <Toggle label="Mock (no model)" checked={mock} onChange={setMock} disabled={running} />
            </div>

            <p className="text-[11px] text-faint leading-relaxed">
              Offset shifts the GPS clock relative to the video (auto-sync runs on top of this; default <span className="text-muted font-medium">-3s</span> for the Berkeley footage).
              A full run over a long video can take several minutes.
            </p>

            <button onClick={run} disabled={running || !video} className="btn-primary w-full justify-center py-2">
              {running
                ? <><Loader2 size={14} className="animate-spin" /> Processing…</>
                : <><Play size={14} /> Run pipeline</>}
            </button>
          </div>
        </div>

        {/* Job log */}
        {(job || running) && (
          <div className="card overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-line bg-panel-2">
              <Terminal size={14} className="text-muted" />
              <span className="text-xs font-semibold text-ink">
                {job?.label ? `Run · ${job.label}` : 'Run'}
              </span>
              <StatusBadge job={job} running={running} />
              {job && <span className="text-xs text-faint tabular-nums ml-auto">{job.elapsed_sec}s</span>}
            </div>

            <div
              ref={logRef}
              className="font-mono text-[11.5px] leading-relaxed text-muted bg-canvas px-4 py-3 max-h-80 overflow-auto whitespace-pre-wrap"
            >
              {logLines.length === 0
                ? <span className="text-faint">Starting…</span>
                : logLines.map((l, i) => (
                    <div key={i} className={l.startsWith('[error]') ? 'text-red-300' : l.startsWith('[post]') ? 'text-emerald-300' : undefined}>
                      {l || '\u00a0'}
                    </div>
                  ))}
            </div>

            {job?.status === 'done' && (
              <div className="flex items-center gap-2 px-4 py-3 border-t border-line bg-panel-2 flex-wrap">
                <CheckCircle2 size={15} className="text-emerald-400" />
                <span className="text-sm text-ink">Done. Operations DB and map updated.</span>
                <div className="flex gap-2 ml-auto">
                  <button onClick={() => onNavigate('map')} className="btn-ghost">View on Map</button>
                  <button onClick={() => onNavigate('analysis')} className="btn-primary">Open Analysis</button>
                </div>
              </div>
            )}
            {job?.status === 'error' && (
              <div className="flex items-center gap-2 px-4 py-3 border-t border-line bg-panel-2">
                <XCircle size={15} className="text-red-400" />
                <span className="text-sm text-red-300">{job.error ?? 'Pipeline failed. See log above.'}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function FileSection({
  title, icon, files, selected, onSelect, allowNone, emptyHint, accept, kind, onUpload, uploading, disabled,
}: {
  title: string
  icon: React.ReactNode
  files: DataFile[]
  selected: string | null
  onSelect: (p: string | null) => void
  allowNone?: boolean
  emptyHint: string
  accept: string
  kind: 'video' | 'gps'
  onUpload: (files: FileList | null, kind: 'video' | 'gps') => void
  uploading: boolean
  disabled?: boolean
}) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-[11px] uppercase tracking-wide text-faint font-semibold flex items-center gap-1.5">
          {icon} {title}
        </span>
        <button
          onClick={() => inputRef.current?.click()}
          disabled={disabled || uploading}
          className="btn-ghost ml-auto !px-2 !py-1"
          title={`Upload ${kind}`}
        >
          <UploadCloud size={12} /> Upload
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={e => { onUpload(e.target.files, kind); e.target.value = '' }}
        />
      </div>

      <div className="space-y-1 max-h-52 overflow-auto pr-0.5">
        {allowNone && (
          <FileRow
            active={selected == null}
            onClick={() => onSelect(null)}
            left={<Ban size={13} className="text-faint" />}
            name="None"
            meta="run without GPS"
          />
        )}
        {files.length === 0 && !allowNone && (
          <div className="text-xs text-faint py-3 px-1">{emptyHint}</div>
        )}
        {files.map(f => (
          <FileRow
            key={f.path}
            active={selected === f.path}
            onClick={() => onSelect(f.path)}
            left={<FolderOpen size={13} className="text-faint" />}
            name={f.name}
            meta={`${f.dir} · ${formatBytes(f.size)}`}
          />
        ))}
      </div>
    </div>
  )
}

function FileRow({ active, onClick, left, name, meta }: {
  active: boolean
  onClick: () => void
  left: React.ReactNode
  name: string
  meta: string
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md border text-left transition-colors ${
        active
          ? 'bg-primary/10 border-primary/40'
          : 'bg-canvas border-line hover:border-line hover:bg-panel-2'
      }`}
    >
      <span className={`grid place-items-center w-4 h-4 rounded-full border ${active ? 'border-primary' : 'border-line'}`}>
        {active && <span className="w-2 h-2 rounded-full bg-primary" />}
      </span>
      {left}
      <span className="min-w-0 flex-1">
        <span className="block text-sm text-ink truncate">{name}</span>
        <span className="block text-[11px] text-faint truncate">{meta}</span>
      </span>
    </button>
  )
}

function Toggle({ label, checked, onChange, disabled }: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <label className={`flex items-center gap-2 text-xs ${disabled ? 'opacity-60' : 'cursor-pointer'}`}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative w-8 h-[18px] rounded-full transition-colors ${checked ? 'bg-primary' : 'bg-panel-3'}`}
      >
        <span
          className={`absolute top-[2px] w-3.5 h-3.5 rounded-full bg-white transition-transform ${checked ? 'translate-x-[16px]' : 'translate-x-[2px]'}`}
        />
      </button>
      <span className="text-muted">{label}</span>
    </label>
  )
}

function StatusBadge({ job, running }: { job: JobStatus | null; running: boolean }) {
  if (running || job?.status === 'running') {
    return (
      <span className="badge bg-primary/15 text-primary">
        <Loader2 size={10} className="animate-spin" /> running
      </span>
    )
  }
  if (job?.status === 'done') return <span className="badge bg-emerald-500/15 text-emerald-300">done</span>
  if (job?.status === 'error') return <span className="badge bg-red-500/15 text-red-300">error</span>
  return null
}
