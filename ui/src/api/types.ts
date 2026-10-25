// Contract types for the Spark MD worker API (docs/build/00-architecture.md v0.8).
// Frozen before parallel work: UI formats numbers only, never computes them.

export type StudyStatus =
  | "received"
  | "organized"
  | "analyzing"
  | "awaiting_confirmation"
  | "analyzed"
  | "reported"
  | "approved"
  | "failed"

export type Priority = "routine" | "elevated" | "urgent"
export type ReportKind = "radiology" | "pcp_letter"

export interface WorklistRow {
  study_uid: string
  patient_id: string
  timepoint: string
  day_offset: number | null
  status: StudyStatus
  priority: Priority
  priority_reason: string | null
  lung_rads: string | null
  received_at: string
  reports_awaiting: number
}

export interface Series {
  series_uid: string
  series_number: number | null
  modality: string | null
  kernel: string | null
  kernel_list: string[] | null
  slice_thickness: number | null
  n_instances: number | null
  image_type: string | null
  axial: boolean
  path: string | null
  eligible: boolean
  eligible_reason: string | null
  fallback: boolean
  selected: boolean
  select_reason: string | null
}

export interface JobProgress {
  job_id: string
  study_uid: string
  state: "queued" | "running" | "done" | "failed"
  stage: string
  stage_index: number
  elapsed_s: number
  study_status?: StudyStatus
}

export interface PriorRef {
  study_uid: string
  timepoint: string
  day_offset: number | null
  status: StudyStatus
  lung_rads: string | null
}

export interface StudyDetail extends WorklistRow {
  series: Series[]
  priors: PriorRef[]
  job: JobProgress | null
}

export interface Proposal {
  source: string // e.g. "A7"
  long_mm: number | null
  short_mm: number | null
  mean_mm: number | null
  box_mean_mm: number | null
}

export interface Confirmation {
  confirmed: boolean
  edited: boolean
  by: string | null
  at: string | null
}

export interface Prior {
  study_uid: string
  interval_days: number | null
  mean_mm: number | null
  volume_mm3: number | null
  delta_mean_mm: number | null
  growth_per_12mo_mm: number | null
  growth_normalized: boolean
  vdt_days: number | null
  growing: boolean | null
}

export interface Nodule {
  nodule_id: string
  track_id: string
  lobe: string | null
  center_mm: [number, number, number] | null
  det_score: number | null
  long_mm: number | null
  short_mm: number | null
  mean_mm: number | null
  volume_mm3: number | null
  proposal: Proposal | null
  confirmation: Confirmation
  mean_hu: number | null
  type: "solid" | "part_solid" | "ggo" | null
  prior: Prior | null
}

export interface Assessment {
  lung_rads: string
  rule_id: string
  driver_nodule_id: string | null
  management: string
  rules_version: string
  growth?: unknown
}

export interface KeySlice {
  name: string
  url: string
  plane: string
  nodule_id: string | null
  box_px: [number, number, number, number] | null
}

export interface NoduleSliceInfo {
  nodule_id: string
  index: number
  box_px: [number, number, number, number] | null
  half_range: number
}

export interface SliceStack {
  count: number
  spacing_mm: number
  z_mm: number[]
  size: [number, number]
  url_pattern: string
  index_digits: number
  nodule_slices: NoduleSliceInfo[]
}

export interface Assets {
  lung_mesh?: string | null
  nodule_mesh?: string | null
  key_slices?: KeySlice[]
  slice_stack?: SliceStack | null
}

export interface Extras {
  emphysema_laa950_pct?: number | null
  vertebra?: { label: string | null; mean_hu: number | null; flag?: string | null } | null
  cac?: { experimental: boolean; agatston?: number | null } | null
}

export interface Findings {
  study_uid: string
  patient_id: string
  timepoint: string
  day_offset: number | null
  series_uid: string | null
  pipeline_version: string
  lung?: { mask_source: string; volume_ml: number | null } | null
  nodules: Nodule[]
  pending_confirmation: string[]
  assessment: Assessment | null
  extras?: Extras | null
  assets: Assets
  placeholder?: boolean
}

export interface Report {
  report_id: string
  study_uid: string
  kind: ReportKind
  markdown: string
  version: number
  status: "draft" | "approved"
  approved_by: string | null
  approved_at: string | null
}

export interface AgentEvent {
  id: number
  ts: string
  study_uid: string | null
  source: "tool_call" | "agent_note" | "system"
  message: string
  tool?: string | null
  status?: number | null
  duration_ms?: number | null
  payload?: unknown
  /** worker history rows carry the raw column; SSE frames flatten it */
  payload_json?: string | null
}

export interface OutboxItem {
  id: number
  ts: string
  report_id: string
  study_uid?: string | null
  patient_id?: string | null
  recipient: string
  subject?: string | null
  kind?: ReportKind
  /** the approved report as delivered (worker stores the full row) */
  payload?: Partial<Report> | null
}

export interface NetStats {
  tx_bytes: number
  rx_bytes: number
  since: string
  /** 10: physical interfaces only (`/sys/class/net/<if>/device`) */
  interfaces: { name: string; up?: boolean; tx_bytes: number; rx_bytes?: number }[]
  link_up: boolean
}

export interface DemoState {
  replaying: boolean
  patient_id: string | null
  timepoint: string | null
  speed: number
  mode?: "live" | "cached"
  waiting_for?: null | "confirm" | "agent" | "approve"
  phase?: string | null
}

export interface ApproveResult {
  report: Report
  outbox_id: number | null
  already_approved: boolean
}

export type ViewerCommand =
  | { command: "show_nodule"; study_uid: string; nodule_id?: string }
  | { command: "compare_prior"; study_uid: string; nodule_id?: string }
  | { command: "reset_view"; study_uid: string }
  | { command: "show_extras"; study_uid: string }

export interface SseEvents {
  agent_log: AgentEvent
  worklist_changed: { reason: "received" | "status" | "priority" | "reset"; study_uid: string | null }
  study_updated: { study_uid: string; status: StudyStatus }
  job_progress: JobProgress
  viewer_command: ViewerCommand
  report_saved: {
    study_uid: string
    report_id: string
    kind: ReportKind
    version: number
    status: "draft" | "approved"
  }
  outbox_delivered: {
    outbox_id: number
    report_id: string
    study_uid: string
    patient_id: string
    recipient: string
    subject: string
  }
  net_stats: NetStats
  demo_state: DemoState
}
export type SseEventType = keyof SseEvents

export interface AskEvent {
  event: "delta" | "tool" | "done" | "error"
  data: { text?: string; ok?: boolean; tool?: string; args?: unknown; message?: string }
}

export interface ConfirmResult {
  nodule_id: string
  long_mm: number
  short_mm: number
  mean_mm: number
  volume_mm3: number | null
  edited: boolean
  confirmed_by: string
  confirmed_at: string
  all_confirmed: boolean
  assessment?: Assessment | null
}
