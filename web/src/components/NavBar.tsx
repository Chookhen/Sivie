import { AlertTriangle, Map, ClipboardList } from 'lucide-react'

export type Page = 'map' | 'analysis'

interface Props {
  page: Page
  onNavigate: (page: Page) => void
}

export default function NavBar({ page, onNavigate }: Props) {
  return (
    <nav className="flex items-center h-11 shrink-0 bg-slate-950 border-b border-slate-700 px-4 gap-4">
      <div className="flex items-center gap-2 mr-2">
        <AlertTriangle size={15} className="text-orange-400 shrink-0" />
        <span className="text-sm font-bold text-white">Road Hazard Monitor</span>
      </div>
      <div className="flex gap-1">
        <button
          onClick={() => onNavigate('map')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
            page === 'map'
              ? 'bg-slate-700 text-white'
              : 'text-slate-400 hover:text-white hover:bg-slate-800'
          }`}
        >
          <Map size={12} />
          Map
        </button>
        <button
          onClick={() => onNavigate('analysis')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
            page === 'analysis'
              ? 'bg-slate-700 text-white'
              : 'text-slate-400 hover:text-white hover:bg-slate-800'
          }`}
        >
          <ClipboardList size={12} />
          Analysis Review
        </button>
      </div>
    </nav>
  )
}
