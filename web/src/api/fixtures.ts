// Simulated backend for `npm run dev:fixtures`: replays the real scenario recorded in web/fixtures/
// (scripts/export_fixtures.py). It is for developing and trying the UI without a backend, not for validating logic.
import audit from '../../fixtures/audit.json'
import approved from '../../fixtures/case_approved.json'
import awaiting from '../../fixtures/case_awaiting_approval.json'
import awaiting2 from '../../fixtures/case_awaiting_approval_2.json'
import confirmed from '../../fixtures/case_confirmed.json'
import created from '../../fixtures/case_created.json'
import diagnosed from '../../fixtures/case_diagnosed.json'
import done from '../../fixtures/case_done.json'
import edited from '../../fixtures/case_edited.json'
import escalated from '../../fixtures/case_escalated.json'
import iter2Ready from '../../fixtures/case_iter2_ready.json'
import ready from '../../fixtures/case_ready.json'
import rejected from '../../fixtures/case_rejected.json'
import health from '../../fixtures/health.json'
import taxonomy from '../../fixtures/taxonomy.json'
import { ApiError, type PrintLoopApi } from './client'
import type { AuditRow, Case, CaseSummary, Health, LiveSession, LiveState, RewindStep, Taxonomy } from './types'

const asCase = (data: unknown) => structuredClone(data) as Case
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

const store = new Map<string, Case>()
const proposals = new Map<string, number>()

/** Recorded state reached by going back to (iteration, step) in the fixture scenario. */
const REWIND: Record<string, unknown> = {
  '1:photos': created,
  '1:diagnosis': ready,
  '1:patch': diagnosed,
  '1:approval': awaiting,
  '2:photos': approved,
  '2:diagnosis': iter2Ready,
}

// Mode 1 in fixture mode: a scripted session, one frame per poll (no detector, no frames on disk).
const LIVE_SCRIPT: string[][] = [[], [], ['stringing'], [], ['spaghetti'], ['spaghetti'], ['spaghetti'], []]
let live: LiveSession | null = null
let liveTick = 0

function liveFrame(): void {
  if (!live || live.status !== 'running') return
  if (liveTick >= LIVE_SCRIPT.length) {
    live.status = 'finished'
    live.ended_at = new Date().toISOString()
    return
  }
  const defects = LIVE_SCRIPT[liveTick]!
  const id = liveTick.toString(16).padStart(16, '0')
  const at = new Date().toISOString()
  live.last = {
    frame_id: id,
    name: `${liveTick.toString().padStart(3, '0')}.jpg`,
    taken_at: at,
    layer_num: null,
    progress: null,
    defects,
    primary: defects[0] ?? 'none',
    model: 'printloop-vision-e4b',
    latency_ms: 740,
    error: null,
    frame_url: `/api/live/frames/${live.id}/${id}`,
  }
  live.counts.frames += 1
  defects.forEach((d) => (live!.counts.positives[d] = (live!.counts.positives[d] ?? 0) + 1))
  if (liveTick === 6) {
    live.alerts.push({
      id: 'a1',
      defect: 'spaghetti',
      level: 'pause_proposed',
      since: at,
      frames: ['4', '5', '6'].map((n) => n.padStart(16, '0')),
      frame_urls: [],
      cleared_at: null,
      dismissed: false,
      dismiss_reason: '',
    })
  }
  liveTick += 1
}

function liveSnapshot(): LiveState {
  return {
    session: live ? structuredClone(live) : null,
    running: live?.status === 'running',
    detector: { mode: 'on', model: 'printloop-vision-e4b', base_url: null },
    printer: { configured: false, linked: false },
    defaults: { source: 'replay', replay_dir: 'data/live/demo', interval_s: 10, snapshot_url: null },
  }
}

function reset(): void {
  store.clear()
  proposals.clear()
  live = null
  liveTick = 0
  const main = asCase(created)
  store.set(main.id, main)
  const other = asCase(escalated)
  store.set(other.id, other)
}
reset()

function get(id: string): Case {
  const found = store.get(id)
  if (!found) throw new ApiError(404, `case ${id} not found`)
  return found
}

function put(id: string, next: unknown): Case {
  const value = asCase(next)
  value.id = id
  store.set(id, value)
  return structuredClone(value)
}

function summary(c: Case): CaseSummary {
  const it = c.iterations[c.iterations.length - 1]
  return {
    id: c.id,
    name: c.name,
    state: c.state,
    outcome: c.outcome,
    iteration: it?.n ?? 1,
    printer: c.printer,
    material: c.material,
    updated_at: c.updated_at,
    defect: it?.diagnosis?.primary ?? null,
    allowed_actions: c.allowed_actions,
  }
}

const iterationOf = (c: Case) => c.iterations.length

export const fixtureApi: PrintLoopApi & { reset: () => void } = {
  reset,
  async health() {
    await delay(150)
    return structuredClone(health) as Health
  },
  async taxonomy() {
    return structuredClone(taxonomy) as Taxonomy
  },
  async listCases() {
    await delay(200)
    return [...store.values()].map(summary)
  },
  async getCase(id) {
    await delay(150)
    return structuredClone(get(id))
  },
  async createCase(_project, name) {
    await delay(900)
    const id = `demo${store.size + 1}`
    const c = put(id, created)
    c.name = name || c.name
    store.set(id, structuredClone(c))
    return c
  },
  async deleteCase(id) {
    await delay(200)
    get(id)
    store.delete(id)
  },
  async uploadPhotos(id) {
    await delay(400)
    const c = get(id)
    return put(id, iterationOf(c) > 1 ? iter2Ready : ready)
  },
  async diagnose(id, req) {
    await delay(req.mode === 'operator' ? 300 : 1500)
    const c = get(id)
    if (iterationOf(c) > 1) return put(id, done)
    return put(id, diagnosed)
  },
  async propose(id) {
    await delay(2200)
    const n = (proposals.get(id) ?? 0) + 1
    proposals.set(id, n)
    return put(id, n === 1 ? awaiting : awaiting2)
  },
  async decide(id, req) {
    await delay(req.edits ? 2000 : 400)
    const c = get(id)
    if (req.stop) {
      const stopped = structuredClone(c)
      stopped.state = 'escalated'
      stopped.outcome = 'stopped'
      stopped.message = `Loop stopped by the operator. ${req.reason}`.trim()
      stopped.allowed_actions = ['rewind']
      return put(id, stopped)
    }
    if (req.edits && !req.approved) return put(id, edited)
    if (req.approved) return put(id, approved)
    if (!req.reason) throw new ApiError(409, 'rejecting a patch requires a reason')
    return put(id, rejected)
  },
  async confirm(id) {
    await delay(300)
    const c = get(id)
    if (!c.allowed_actions.includes('confirm_success')) {
      throw new ApiError(409, 'only the reprint of an approved patch can be confirmed')
    }
    return put(id, confirmed)
  },
  async rewind(id, iteration, step: RewindStep) {
    await delay(300)
    const target = REWIND[`${iteration}:${step}`]
    if (!target) throw new ApiError(409, `cannot go back to '${step}' of iteration ${iteration} in fixture mode`)
    if (iteration === 1 && step !== 'approval') proposals.set(id, 0)
    const next = asCase(target)
    next.name = get(id).name
    return put(id, next)
  },
  async audit() {
    return structuredClone(audit) as AuditRow[]
  },
  async live() {
    await delay(100)
    liveFrame()
    return liveSnapshot()
  },
  async liveStart(req) {
    await delay(200)
    if (live?.status === 'running') throw new ApiError(409, 'a live session is already running: stop it first')
    liveTick = 0
    live = {
      id: 'demo-live',
      status: 'running',
      source: { kind: req.source, detail: req.replay_dir ?? req.url ?? 'P1S' },
      interval_s: req.interval_s ?? 10,
      record_all: false,
      case_id: req.case_id ?? null,
      started_at: new Date().toISOString(),
      ended_at: null,
      error: '',
      thresholds: { pause_k: 3, pause_n: 4, alert_k: 4, alert_n: 6, clear_n: 6 },
      printer: { linked: false },
      detector: { model: 'printloop-vision-e4b', calls: 0, errors: 0, latency_p50_ms: 740 },
      last: null,
      alerts: [],
      counts: { frames: 0, skipped: 0, errors: 0, positives: {} },
    }
    return structuredClone(live)
  },
  async liveStop() {
    await delay(150)
    if (live?.status !== 'running') throw new ApiError(409, 'no live session is running')
    live.status = 'stopped'
    live.ended_at = new Date().toISOString()
    return structuredClone(live)
  },
  async liveDismiss(alertId, reason) {
    const alert = live?.alerts.find((a) => a.id === alertId)
    if (!live || !alert) throw new ApiError(409, `alert ${alertId} not found`)
    alert.dismissed = true
    alert.dismiss_reason = reason
    return structuredClone(live)
  },
  async liveAttach(caseId) {
    await delay(300)
    return structuredClone(get(caseId))
  },
}
