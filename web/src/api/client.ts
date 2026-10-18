import type {
  AuditRow,
  Case,
  CaseSummary,
  DecisionRequest,
  DiagnoseRequest,
  Health,
  LiveSession,
  LiveStartRequest,
  LiveState,
  RewindStep,
  Taxonomy,
} from './types'

/** API error carrying the backend's readable message (`{"detail": "..."}`). */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Something other than PrintLoop answers on the API port. */
export class WrongBackendError extends ApiError {
  constructor() {
    super(0, 'A backend other than PrintLoop answers on the configured port: check PRINTLOOP_API.')
    this.name = 'WrongBackendError'
  }
}

export interface PrintLoopApi {
  health(): Promise<Health>
  taxonomy(): Promise<Taxonomy>
  listCases(): Promise<CaseSummary[]>
  getCase(id: string): Promise<Case>
  createCase(project: File, name: string): Promise<Case>
  deleteCase(id: string): Promise<void>
  uploadPhotos(id: string, photos: File[], note: string): Promise<Case>
  diagnose(id: string, req: DiagnoseRequest): Promise<Case>
  propose(id: string): Promise<Case>
  decide(id: string, req: DecisionRequest): Promise<Case>
  confirm(id: string, note: string): Promise<Case>
  rewind(id: string, iteration: number, step: RewindStep): Promise<Case>
  live(): Promise<LiveState>
  liveStart(req: LiveStartRequest): Promise<LiveSession>
  liveStop(): Promise<LiveSession>
  liveDismiss(alertId: string, reason: string): Promise<LiveSession>
  liveAttach(caseId: string, sessionId?: string): Promise<Case>
  audit(id: string): Promise<AuditRow[]>
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'Backend unreachable: start it with `uv run uvicorn printloop.api:app --port 8788`.')
  }
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body: unknown = await res.json()
      if (body && typeof body === 'object' && 'detail' in body) {
        const detail = (body as { detail: unknown }).detail
        message = typeof detail === 'string' ? detail : JSON.stringify(detail)
      }
    } catch {
      // not a JSON reply: keep the HTTP status
    }
    throw new ApiError(res.status, message)
  }
  return (await res.json()) as T
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

/** Another backend (e.g. MarginSwarm) may answer on the same port: recognise ours by the shape of /health. */
async function health(): Promise<Health> {
  const body = await request<Partial<Health>>('/api/health')
  if (!body.slicer || !body.llm) {
    throw new WrongBackendError()
  }
  return body as Health
}

export const httpApi: PrintLoopApi = {
  health,
  taxonomy: () => request('/api/taxonomy'),
  listCases: () => request('/api/cases'),
  getCase: (id) => request(`/api/cases/${encodeURIComponent(id)}`),
  createCase: (project, name) => {
    const form = new FormData()
    form.append('project', project)
    form.append('name', name)
    return request('/api/cases', { method: 'POST', body: form })
  },
  deleteCase: async (id) => {
    await request(`/api/cases/${encodeURIComponent(id)}`, { method: 'DELETE' })
  },
  uploadPhotos: (id, photos, note) => {
    const form = new FormData()
    photos.forEach((p) => form.append('photos', p))
    form.append('note', note)
    return request(`/api/cases/${encodeURIComponent(id)}/photos`, { method: 'POST', body: form })
  },
  diagnose: (id, req) => request(`/api/cases/${encodeURIComponent(id)}/diagnose`, json(req)),
  propose: (id) => request(`/api/cases/${encodeURIComponent(id)}/propose`, json({ mode: 'auto' })),
  decide: (id, req) => request(`/api/cases/${encodeURIComponent(id)}/decision`, json(req)),
  confirm: (id, note) => request(`/api/cases/${encodeURIComponent(id)}/confirm`, json({ note })),
  rewind: (id, iteration, step) => request(`/api/cases/${encodeURIComponent(id)}/rewind`, json({ iteration, step })),
  audit: (id) => request(`/api/cases/${encodeURIComponent(id)}/audit`),
  live: () => request('/api/live'),
  liveStart: (req) => request('/api/live/start', json(req)),
  liveStop: () => request('/api/live/stop', { method: 'POST' }),
  liveDismiss: (alertId, reason) =>
    request(`/api/live/alerts/${encodeURIComponent(alertId)}/dismiss`, json({ reason })),
  liveAttach: (caseId, sessionId) => request('/api/live/attach', json({ case_id: caseId, session_id: sessionId })),
}
