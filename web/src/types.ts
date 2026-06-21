export type PriorityLabel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
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
}

export interface DetectionReport {
  source: string
  generated_at: string
  frame_count: number
  detections: Detection[]
}
