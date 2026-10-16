import { httpApi, type PrintLoopApi } from './client'

export { ApiError, WrongBackendError } from './client'
export type { PrintLoopApi } from './client'

/** true con `npm run dev:fixtures`: la UI usa le risposte registrate, senza backend. */
export const USE_FIXTURES = import.meta.env.MODE === 'fixtures'

let fixtures: Promise<PrintLoopApi> | null = null
// Import dinamico: le fixture non finiscono nel bundle di produzione.
const loadFixtures = () => (fixtures ??= import('./fixtures').then((m) => m.fixtureApi))

function lazy(load: () => Promise<PrintLoopApi>): PrintLoopApi {
  return {
    health: () => load().then((a) => a.health()),
    taxonomy: () => load().then((a) => a.taxonomy()),
    listCases: () => load().then((a) => a.listCases()),
    getCase: (id) => load().then((a) => a.getCase(id)),
    createCase: (project, name) => load().then((a) => a.createCase(project, name)),
    uploadPhotos: (id, photos, note) => load().then((a) => a.uploadPhotos(id, photos, note)),
    diagnose: (id, req) => load().then((a) => a.diagnose(id, req)),
    propose: (id) => load().then((a) => a.propose(id)),
    decide: (id, req) => load().then((a) => a.decide(id, req)),
    audit: (id) => load().then((a) => a.audit(id)),
  }
}

export const api: PrintLoopApi = USE_FIXTURES ? lazy(loadFixtures) : httpApi
