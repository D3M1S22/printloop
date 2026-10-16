import type { CaseState, Check, Outcome, Value } from '../api/types'

export const STATE_LABEL: Record<CaseState, string> = {
  awaiting_photos: 'In attesa di foto',
  ready: 'Pronto per l’analisi',
  needs_info: 'Servono informazioni',
  diagnosed: 'Diagnosticato',
  awaiting_approval: 'Da approvare',
  escalated: 'Passato all’operatore',
  done: 'Chiuso',
}

/** Tono del badge di stato: guida il colore, il testo resta sempre visibile. */
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
  fixed: 'Difetto corretto',
  no_defect: 'Nessun difetto',
  escalated: 'Escalation',
  stopped: 'Fermato dall’operatore',
}

export const SEVERITY_LABEL = ['assente', 'lieve', 'evidente', 'grave'] as const

export const SOURCE_LABEL = { llm: 'Gemma 4', rules: 'regole KB', operator: 'operatore' } as const

export const CHECK_LABEL: Record<string, string> = {
  config: 'Valore nel G-code',
  feature_speed: 'Velocità della feature',
  first_layer_speed: 'Velocità primo layer',
  extrusion_per_mm: 'Estrusione per mm',
  fan_during: 'Ventola sulla feature',
  hotend_setpoint: 'Temperatura ugello',
  bed_setpoint: 'Temperatura piano',
  retraction: 'Retrazione',
  feature_length: 'Estensione feature',
  volumetric_limit: 'Limite volumetrico',
  max_volumetric_speed: 'Flusso volumetrico',
  nozzle_range: 'Range del filamento',
  bed_max: 'Massimo del piano',
}

const nf = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 3 })

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

/** "+10 s", "−0,13 g", "invariato": variazione leggibile tra prima e dopo la patch. */
export function delta(pair: [number | null, number | null] | undefined, kind: 'time' | 'grams'): string {
  if (!pair || pair[0] === null || pair[1] === null) return '—'
  const diff = pair[1] - pair[0]
  if (Math.abs(diff) < (kind === 'time' ? 0.5 : 0.005)) return 'invariato'
  const sign = diff > 0 ? '+' : '−'
  const abs = Math.abs(diff)
  return kind === 'time' ? `${sign}${duration(abs)}` : `${sign}${nf.format(Number(abs.toFixed(2)))} g`
}

export function dateTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString('it-IT', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function checkLabel(check: Check): string {
  return CHECK_LABEL[check.check] ?? check.check
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}
