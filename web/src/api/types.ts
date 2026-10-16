// Tipi dell'API PrintLoop: rispecchiano src/printloop/models.py e i campi derivati di api.view().
// Contratto: docs/printloop/05_API.md.

export type DefectClass =
  | 'under_extrusion'
  | 'over_extrusion'
  | 'stringing'
  | 'bridge_sagging'
  | 'overhang_curling'
  | 'warping'
  | 'first_layer'
  | 'layer_shift'
  | 'spaghetti'
  | 'none'
  | 'other'

export type CaseState =
  'awaiting_photos' | 'ready' | 'needs_info' | 'diagnosed' | 'awaiting_approval' | 'escalated' | 'done'

export type Action =
  'upload_photos' | 'diagnose' | 'diagnose_operator' | 'propose' | 'approve' | 'reject' | 'edit' | 'stop'

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
}

export interface Health {
  status: string
  version: string
  llm: { mode: 'llm' | 'offline'; model: string | null; base_url: string | null }
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
