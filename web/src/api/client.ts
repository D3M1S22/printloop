import type { AuditRow, Case, CaseSummary, DecisionRequest, DiagnoseRequest, Health, Taxonomy } from './types'

/** Errore dell'API con il messaggio leggibile del backend (`{"detail": "..."}`). */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Sulla porta API risponde un servizio che non è PrintLoop. */
export class WrongBackendError extends ApiError {
  constructor() {
    super(0, 'Sulla porta configurata risponde un backend diverso da PrintLoop: controllare PRINTLOOP_API.')
    this.name = 'WrongBackendError'
  }
}

export interface PrintLoopApi {
  health(): Promise<Health>
  taxonomy(): Promise<Taxonomy>
  listCases(): Promise<CaseSummary[]>
  getCase(id: string): Promise<Case>
  createCase(project: File, name: string): Promise<Case>
  uploadPhotos(id: string, photos: File[], note: string): Promise<Case>
  diagnose(id: string, req: DiagnoseRequest): Promise<Case>
  propose(id: string): Promise<Case>
  decide(id: string, req: DecisionRequest): Promise<Case>
  audit(id: string): Promise<AuditRow[]>
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'Backend non raggiungibile: avviare `uv run uvicorn printloop.api:app --port 8788`.')
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
      // risposta non JSON: resta il codice HTTP
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

/** Sulla stessa porta può rispondere un altro backend (es. MarginSwarm): lo riconosciamo dalla forma di /health. */
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
  uploadPhotos: (id, photos, note) => {
    const form = new FormData()
    photos.forEach((p) => form.append('photos', p))
    form.append('note', note)
    return request(`/api/cases/${encodeURIComponent(id)}/photos`, { method: 'POST', body: form })
  },
  diagnose: (id, req) => request(`/api/cases/${encodeURIComponent(id)}/diagnose`, json(req)),
  propose: (id) => request(`/api/cases/${encodeURIComponent(id)}/propose`, json({ mode: 'auto' })),
  decide: (id, req) => request(`/api/cases/${encodeURIComponent(id)}/decision`, json(req)),
  audit: (id) => request(`/api/cases/${encodeURIComponent(id)}/audit`),
}
