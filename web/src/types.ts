export type PriorityLabel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'

export interface POI {
  name: string | null
  category: string
  distance_m: number
}

export type IssueType = 'pothole' | 'crack' | 'obscured_sign' | 'faded_marking' | 'debris' | 'other'
export type RoadContext = 'freeway' | 'arterial' | 'residential' | 'unknown'

export interface Detection {
  type: IssueType
  description: string
  severity: number
  confidence: number
  road_context: RoadContext
  frame: string
  timestamp_offset_sec: number
  priority: number
  priority_label: PriorityLabel
  lat: number | null
  lng: number | null
  image_url?: string | null
  road_name?: string | null
  road_class?: string | null
  nearby_pois?: POI[]
  priority_multiplier?: number | null
  final_priority?: number | null
  justification?: string[] | null
  box_2d?: [number, number, number, number] | null
  street_hazard_count?: number | null
  street_pothole_count?: number | null
  street_crack_count?: number | null
  street_weight?: number | null
  hazard_id?: string | null
  times_seen?: number | null
}

export interface DetectionReport {
  source: string
  generated_at: string
  frame_count: number
  gps_source?: string | null
  detections: Detection[]
}

export interface Occurrence {
  id: string
  type: IssueType
  description: string
  severity: number
  score: number
  confidence?: number | null
  road_name?: string | null
  road_context?: RoadContext | null
  frame?: string | null
  image_url?: string | null
  lat: number | null
  lng: number | null
  justification?: string[]
  priority_multiplier?: number | null
  times_seen?: number
  source: 'detection' | 'manual'
  status: 'open' | 'resolved'
  created_at?: string
}

export interface OccurrenceDB {
  backend?: string
  location_available: boolean
  source_video?: string | null
  count: number
  located_count: number
  occurrences: Occurrence[]
}

export interface NewOccurrence {
  type: IssueType
  description?: string
  severity?: number
  score?: number | null
  lat?: number | null
  lng?: number | null
  road_name?: string | null
  road_context?: RoadContext | null
}

export interface ModelDataset {
  key: string
  label: string
  sublabel: string
  detections: Detection[]
}

export interface DataFile {
  name: string
  path: string
  dir: string
  size: number
  modified: number
  kind: 'video' | 'gps'
}

export interface FileListing {
  videos: DataFile[]
  gps: DataFile[]
  upload_dir: string
}

export interface ProcessOptions {
  video: string
  gps?: string | null
  time_offset?: number
  no_auto_sync?: boolean
  fps?: number
  max_frames?: number | null
  detector?: 'yolo' | 'gemini'
  yolo_conf?: number
  min_confidence?: number
  mock?: boolean
  mock_gps?: boolean
  dedupe?: boolean
  enrich?: boolean
  ai_priority?: boolean
  ai_mock?: boolean
}

export interface JobStatus {
  id: string
  label: string
  status: 'running' | 'done' | 'error'
  returncode: number | null
  error: string | null
  started_at: number
  ended_at: number | null
  elapsed_sec: number
  log: string[]
  next_offset: number
}
