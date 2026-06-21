export type PriorityLabel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'

export interface POI {
  name: string
  category: string
  distance: number
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
  justification?: string | null
}

export interface DetectionReport {
  source: string
  generated_at: string
  frame_count: number
  detections: Detection[]
}
