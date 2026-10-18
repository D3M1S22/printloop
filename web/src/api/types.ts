// PrintLoop API types: they mirror src/printloop/models.py and the fields derived by api.view().
// Contract: docs/printloop/05_API.md.

export type DefectClass =
  | 'under_extrusion'
  | 'over_extrusion'
  | 'stringing'
  | 'bridge_sagging'
  | 'overhang_curling'
  | 'layer_separation'
  | 'blobs'
  | 'warping'
  | 'first_layer'
  | 'layer_shift'
  | 'spaghetti'
  | 'none'
  | 'other'

export type CaseState =
  'awaiting_photos' | 'ready' | 'needs_info' | 'diagnosed' | 'awaiting_approval' | 'escalated' | 'done'

export type Action =
  | 'upload_photos'
  | 'diagnose'
  | 'diagnose_operator'
  | 'propose'
  | 'approve'
  | 'reject'
  | 'edit'
  | 'stop'
  | 'confirm_success'
  | 'rewind'

/** Steps of one iteration: rewinding to a step puts the case back in the state that waits for it. */
export type RewindStep = 'photos' | 'diagnosis' | 'patch' | 'approval'

export interface RewindTarget {
  iteration: number
  step: RewindStep
  /** What going back throws away, in plain words (files are archived in the case folder, not deleted). */
  discards: string[]
}

export type Outcome = 'fixed' | 'no_defect' | 'escalated' | 'stopped'
export type Source = 'llm' | 'rules' | 'operator'
export type CheckStatus = 'pass' | 'fail' | 'n/a'

export interface Evidence {
  photo: string
  description: string
}

export interface Finding {
  defect: DefectClass
  severity: number
  confidence: number
  evidence: Evidence[]
  location: string
}

/** E4B detector answer for one uploaded photo (09_MODE2_TWO_MODELS.md). */
export interface PhotoDetection {
  photo: string
  defects: string[]
  primary: string
  model: string | null
  latency_ms: number | null
  error: string | null
}

export interface DetectorSummary {
  defects: string[]
  primary: string
  agreement: 'agree' | 'disagree' | 'unavailable'
  photos: number
}

export interface Diagnosis {
  findings: Finding[]
  primary: DefectClass
  primary_label: string
  severity: number
  confidence: number
  needs_more_info: boolean
  question_for_operator: string
  source: 'llm' | 'operator'
  model: string | null
  latency_ms: number | null
  note: string
  detector: DetectorSummary | null
  at: string
}

export type Value = number | string

export interface Change {
  key: string
  before: Value | null
  after: Value
  reason: string
  real: Record<string, Value>
  companion: boolean
  label: string
  unit: string
}

export interface Attempt {
  source: Source
  changes: Change[]
  stage: 'validation' | 'slicing' | 'preflight'
  reason: string
}

export interface Proposal {
  defect: DefectClass
  changes: Change[]
  rationale: string
  expected_effect: string
  source: Source
  model: string | null
  latency_ms: number | null
  rejected_attempts: Attempt[]
  at: string
}

export interface Validation {
  ok: boolean
  errors: string[]
  warnings: string[]
}

export interface Check {
  check: string
  key: string | null
  target: string
  before: number | null
  after: number | null
  expected: string
  status: CheckStatus
  detail: string
}

export interface SideEffects {
  print_time_s?: [number | null, number | null]
  filament_g?: [number | null, number | null]
  layers?: [number | null, number | null]
}

export interface Preflight {
  ok: boolean
  checks: Check[]
  limits: Check[]
  side_effects: SideEffects
}

export interface Decision {
  approved: boolean
  reason: string
  actor: string
  edited: boolean
  override_preflight: boolean
  stop: boolean
  at: string
}

export interface Confirmation {
  note: string
  actor: string
  at: string
}

export interface RejectedProposal {
  proposal: Proposal
  reason: string
  at: string
}

export interface Iteration {
  n: number
  project: string
  source_gcode: string
  photos: string[]
  photo_urls: string[]
  detections: PhotoDetection[]
  note: string
  diagnosis: Diagnosis | null
  proposal: Proposal | null
  validation: Validation | null
  preflight: Preflight | null
  patched_project: string | null
  sliced_3mf: string | null
  print_file_url: string | null
  project_url: string
  slice: { print_time_s?: number | null; slice_elapsed_s?: number } | null
  decision: Decision | null
  rejected: RejectedProposal[]
  confirmed: Confirmation | null
}

export interface EditOption {
  key: string
  label: string
  unit: string
  step: number
  direction: 'up' | 'down'
  min: number
  max: number
  current: number
  proposed: number | null
}

export interface Baseline {
  print_time_s?: number | null
  filament_g?: number
  sliced_3mf?: string
  slicer?: string // slicer that created the project, used for every slice of the case
  notes?: string[] // e.g. fallback to another slicer
}

export interface Case {
  id: string
  name: string
  state: CaseState
  created_at: string
  updated_at: string
  printer: string | null
  material: string | null
  process: string | null
  max_iterations: number
  baseline: Baseline
  iterations: Iteration[]
  rejected_keys: string[]
  outcome: Outcome | null
  message: string
  allowed_actions: Action[]
  /** Earlier steps the case can go back to, oldest first: the last one is "one step back". */
  rewind_targets: RewindTarget[]
  llm_mode: 'llm' | 'offline'
  latest_print_file_url: string | null
  edit_options: EditOption[]
}

export interface CaseSummary {
  id: string
  name: string
  state: CaseState
  outcome: Outcome | null
  iteration: number
  printer: string | null
  material: string | null
  updated_at: string
  defect: DefectClass | null
  allowed_actions: Action[]
}

export interface Health {
  status: string
  version: string
  llm: { mode: 'llm' | 'offline'; model: string | null; base_url: string | null }
  vision_llm?: { mode: 'on' | 'off'; model: string | null; base_url: string | null }
  mode2_detector?: boolean
  warnings?: string[]
  telemetry: { calls: number; errors: number; latency_p50_ms: number | null; latency_p95_ms: number | null }
  slicer: { available: boolean; version: string | null }
  max_iterations: number
  min_confidence: number
}

export interface TaxonomyDefect {
  id: DefectClass
  label: string
  description: string
  fixable: boolean
}

export interface Taxonomy {
  defects: TaxonomyDefect[]
  severity: Record<string, string>
}

export interface AuditRow {
  ts: string
  case_id: string
  iteration: number
  state: CaseState
  event: string
  actor: string
  [extra: string]: unknown
}

export interface DiagnoseRequest {
  mode: 'auto' | 'llm' | 'operator'
  defect?: DefectClass
  severity?: number
  note?: string
}

export interface DecisionRequest {
  approved: boolean
  reason: string
  edits?: Record<string, number>
  stop?: boolean
}

// --- Mode 1: live monitoring (docs/printloop/08_MODE1_LIVE.md) ----------------------------------------------

export type LiveSourceKind = 'replay' | 'p1s' | 'url'

export interface LiveDetection {
  frame_id: string
  name: string
  taken_at: string
  layer_num: number | null
  progress: number | null
  defects: string[]
  primary: string
  model: string | null
  latency_ms: number | null
  error: string | null
  frame_url?: string
}

export interface LiveAlert {
  id: string
  defect: string
  level: 'warning' | 'pause_proposed'
  since: string
  frames: string[]
  frame_urls: string[]
  cleared_at: string | null
  dismissed: boolean
  dismiss_reason: string
}

export interface LiveSession {
  id: string
  status: 'running' | 'stopped' | 'finished' | 'error'
  source: { kind?: LiveSourceKind; detail?: string }
  interval_s: number
  record_all: boolean
  case_id: string | null
  started_at: string
  ended_at: string | null
  error: string
  thresholds: Record<string, number>
  printer: { linked: boolean; [key: string]: unknown }
  detector: { model?: string; calls?: number; errors?: number; latency_p50_ms?: number | null }
  last: LiveDetection | null
  alerts: LiveAlert[]
  counts: { frames: number; skipped: number; errors: number; positives: Record<string, number> }
}

export interface LiveState {
  session: LiveSession | null
  running: boolean
  detector: { mode: 'on' | 'off'; model: string | null; base_url: string | null }
  printer: { configured: boolean; linked: boolean }
  defaults: { source: LiveSourceKind; replay_dir: string | null; interval_s: number; snapshot_url: string | null }
}

export interface LiveStartRequest {
  source: LiveSourceKind
  replay_dir?: string
  url?: string
  interval_s?: number
  case_id?: string
  record_all?: boolean
}
