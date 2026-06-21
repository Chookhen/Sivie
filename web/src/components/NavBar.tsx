import { Map, ClipboardList, Database, Waypoints, FolderCog } from 'lucide-react'

export type Page = 'map' | 'analysis' | 'database' | 'processing'

interface Status {
  online: boolean
  backend?: string
  count?: number
}

interface Props {
  page: Page
  onNavigate: (page: Page) => void
  status?: Status
}

const TABS: { key: Page; label: string; icon: typeof Map }[] = [
  { key: 'map', label: 'Map', icon: Map },
  { key: 'database', label: 'Operations DB', icon: Database },
  { key: 'analysis', label: 'Analysis Review', icon: ClipboardList },
  { key: 'processing', label: 'Processing', icon: FolderCog },
]

export default function NavBar({ page, onNavigate, status }: Props) {
  return (
    <nav className="flex items-center h-14 shrink-0 bg-panel-2 border-b border-line px-4 gap-5">
      <div className="flex items-center gap-2.5 mr-1">
        <div className="grid place-items-center w-8 h-8 rounded-lg bg-primary/15 border border-primary/30">
          <Waypoints size={17} className="text-primary" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-bold text-ink tracking-tight">Sivic</div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-faint">Road Integrity Operations</div>
        </div>
      </div>

      <div className="flex gap-0.5 p-0.5 rounded-lg bg-canvas border border-line">
        {TABS.map(({ key, label, icon: Icon }) => {
          const active = page === key
          return (
            <button
              key={key}
              onClick={() => onNavigate(key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                active
                  ? 'bg-primary/15 text-primary'
                  : 'text-muted hover:text-ink hover:bg-panel-3'
              }`}
            >
              <Icon size={13} />
              {label}
            </button>
          )
        })}
      </div>

      {status && (
        <div className="ml-auto flex items-center gap-3 text-xs">
          {typeof status.count === 'number' && status.online && (
            <span className="text-muted tabular-nums hidden sm:inline">
              <span className="text-ink font-semibold">{status.count}</span> hazards
            </span>
          )}
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-canvas border border-line">
            <span
              className={`w-1.5 h-1.5 rounded-full ${status.online ? 'bg-emerald-400' : 'bg-red-400'}`}
              style={status.online ? { boxShadow: '0 0 0 3px rgba(52,211,153,0.18)' } : undefined}
            />
            <span className="text-muted">
              {status.online
                ? status.backend === 'supabase' ? 'Live · Supabase' : 'Live · Local'
                : 'Offline'}
            </span>
          </span>
        </div>
      )}
    </nav>
  )
}
