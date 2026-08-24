export type Severity = 'normal' | 'info' | 'warning' | 'critical'
export type Position = 'N' | 'R' | 'transit' | 'unknown'

export interface Prediction {
  fault: string
  fault_ko: string
  fault_en: string
  err_code: string | null
  confidence: number
  prediction_set: string[]
  set_size: number
  anomaly_score: number
  severity: Severity
}

export interface EventSummary {
  id: string
  machine_id: string
  ts: string
  direction: 'N' | 'R'
  completed: boolean
  throw_samples: number
  n_samples: number
  health: number
  truth: string
  prediction: Prediction
}

export interface Channel { name: string; unit: string; values: (number | null)[] }
export interface Phase { name: string; start: number; end: number }
export interface Attribution { feature: string; label: string; value: number; contribution: number }
export interface EventDetail extends EventSummary {
  channels: Channel[]
  phases: Phase[]
  attributions: Attribution[]
}

export interface Health {
  health: number
  rul_cycles: number | null
  rul_low: number | null
  rul_high: number | null
  trend: number[]
}

export interface Machine {
  id: string
  label: string
  spec: string
  position: Position
  severity: Severity
  last_event_at: string | null
  events_today: number
  health: Health
  x: number
  y: number
}

export interface Alert {
  id: string
  machine_id: string
  event_id: string
  ts: string
  severity: Severity
  fault: string
  fault_ko: string
  message: string
  state: 'open' | 'acknowledged' | 'resolved'
  assignee: string | null
}

export interface Stats {
  machines: number
  normal: number
  info: number
  warning: number
  critical: number
  events_streamed: number
  open_alerts: number
  model_version: string
  model_source: 'trained' | 'heuristic'
  stream_interval_s: number
}
