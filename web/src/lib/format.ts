import type { CaseState, Check, Outcome, Value } from '../api/types'

export const STATE_LABEL: Record<CaseState, string> = {
  awaiting_photos: 'Awaiting photos',
  ready: 'Ready for analysis',
  needs_info: 'Needs information',
  diagnosed: 'Diagnosed',
  awaiting_approval: 'Awaiting approval',
  escalated: 'Handed to operator',
  done: 'Closed',
}

/** Tone of the state badge: drives the colour, the text is always visible. */
export const STATE_TONE: Record<CaseState, 'neutral' | 'info' | 'warn' | 'accent' | 'ok' | 'danger'> = {
  awaiting_photos: 'neutral',
  ready: 'info',
  needs_info: 'warn',
  diagnosed: 'info',
  awaiting_approval: 'accent',
  escalated: 'danger',
  done: 'ok',
}

export const OUTCOME_LABEL: Record<Outcome, string> = {
  fixed: 'Defect fixed',
  no_defect: 'No defect',
  escalated: 'Escalated',
  stopped: 'Stopped by the operator',
}

export const SEVERITY_LABEL = ['absent', 'minor', 'clear', 'severe'] as const

export const SOURCE_LABEL = { llm: 'Gemma 4', rules: 'KB rules', operator: 'operator' } as const

export const CHECK_LABEL: Record<string, string> = {
  config: 'Value in the G-code',
  feature_speed: 'Feature speed',
  first_layer_speed: 'First layer speed',
  extrusion_per_mm: 'Extrusion per mm',
  fan_during: 'Fan on the feature',
  hotend_setpoint: 'Nozzle temperature',
  bed_setpoint: 'Bed temperature',
  retraction: 'Retraction',
  feature_length: 'Feature extent',
  volumetric_limit: 'Volumetric limit',
  max_volumetric_speed: 'Volumetric flow',
  nozzle_range: 'Filament range',
  bed_max: 'Bed maximum',
  slicer_ui: 'Visible in the slicer',
}

const nf = new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 })

export function num(value: Value | null | undefined, unit = ''): string {
  if (value === null || value === undefined) return '—'
  const text = typeof value === 'number' ? nf.format(value) : value
  return unit && unit !== 'x' ? `${text} ${unit}` : unit === 'x' ? `${text}×` : text
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  const total = Math.round(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h) return `${h} h ${m} min`
  if (m) return `${m} min ${s.toString().padStart(2, '0')} s`
  return `${s} s`
}

/** "+10 s", "−0.13 g", "unchanged": readable change between before and after the patch. */
export function delta(pair: [number | null, number | null] | undefined, kind: 'time' | 'grams'): string {
  if (!pair || pair[0] === null || pair[1] === null) return '—'
  const diff = pair[1] - pair[0]
  if (Math.abs(diff) < (kind === 'time' ? 0.5 : 0.005)) return 'unchanged'
  const sign = diff > 0 ? '+' : '−'
  const abs = Math.abs(diff)
  return kind === 'time' ? `${sign}${duration(abs)}` : `${sign}${nf.format(Number(abs.toFixed(2)))} g`
}

export function dateTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function checkLabel(check: Check): string {
  return CHECK_LABEL[check.check] ?? check.check
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}
