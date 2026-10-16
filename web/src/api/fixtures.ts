// Backend simulato per `npm run dev:fixtures`: ripercorre lo scenario reale registrato in web/fixtures/
// (scripts/export_fixtures.py). Serve a sviluppare e provare la UI senza backend, non a validare la logica.
import audit from '../../fixtures/audit.json'
import approved from '../../fixtures/case_approved.json'
import awaiting from '../../fixtures/case_awaiting_approval.json'
import awaiting2 from '../../fixtures/case_awaiting_approval_2.json'
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
import type { AuditRow, Case, CaseSummary, Health, Taxonomy } from './types'

const asCase = (data: unknown) => structuredClone(data) as Case
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

const store = new Map<string, Case>()
const proposals = new Map<string, number>()

function reset(): void {
  store.clear()
  proposals.clear()
  const main = asCase(created)
  store.set(main.id, main)
  const other = asCase(escalated)
  store.set(other.id, other)
}
reset()

function get(id: string): Case {
  const found = store.get(id)
  if (!found) throw new ApiError(404, `caso ${id} non trovato`)
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
      stopped.message = `Loop fermato dall'operatore. ${req.reason}`.trim()
      stopped.allowed_actions = []
      return put(id, stopped)
    }
    if (req.edits && !req.approved) return put(id, edited)
    if (req.approved) return put(id, approved)
    if (!req.reason) throw new ApiError(409, 'per rifiutare una patch serve una motivazione')
    return put(id, rejected)
  },
  async audit() {
    return structuredClone(audit) as AuditRow[]
  },
}
