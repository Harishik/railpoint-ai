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
  /** How many throws have raised this same condition on this machine. */
  count: number
  /** When it was last seen, as distinct from when it was first raised. */
  last_ts: string | null
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

export type CopilotReply = {
  answer: string
  /** Which path produced the text. Shown in the UI: a work order whose
   *  provenance is unclear is one nobody should sign. */
  source: 'claude' | 'deterministic'
  model: string | null
  citations: string[]
  disclaimer: string
}

export interface ModelCard {
  serving: { source: string; version: string; degraded: boolean; calibration_error?: string | null }
  summary: {
    params: number
    /** Fixed input grid the encoder sees, in samples. */
    window: number
    best_epoch: number
    test: { model: string; accuracy: number; balanced_acc: number; macro_f1: number; weighted_f1: number }
    conformal: {
      alpha: number; qhat: number; coverage: number; mean_set_size: number
      /** Score function the quantile belongs to: 'raps' | 'aps' | 'thr'. */
      rule?: string
      lam?: number
      k_reg?: number
      /** Only written by artefacts calibrated under the plain threshold rule. */
      threshold_empty_sets?: number
      /* Whether set size means anything. Marginal coverage cannot tell: the
         threshold rule hit 0.978 with every set exactly the argmax. */
      singleton_rate?: number
      max_set_size?: number
      /** When top-1 is wrong, how often the truth is still in the set. */
      coverage_when_wrong?: number | null
      error_rate?: number
      error_rate_singleton?: number | null
      error_rate_widened?: number | null
      widened_lift?: number
      calib_events?: number
      calib_machines?: number
      /** Which split the quantile was fitted on. Never the one early stopping used. */
      calib_split?: string
    }
    rul: { n: number; rmse: number; mae: number; interval_halfwidth: number; coverage: number }
    anomaly: {
      roc_auc: number; positive_rate: number
      /** Where healthy held-out (calib) throws sit on the anomaly scale. */
      healthy_calib_n?: number
      healthy_calib_p99?: number
      healthy_calib_p999?: number
      healthy_calib_max?: number
    }
    /** Null when the run had no access to the private Sehwa extract. */
    acceptance: {
      diagnostic_correct: number; diagnostic_total: number
      all_correct: number; passed: boolean; expected_in_conformal_set: number
    } | null
  } | null
  metropt: Record<string, string | number> | null
  acceptance: Record<string, string>[]
  per_class: Record<string, string>[]
}
