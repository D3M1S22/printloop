import { httpApi, type PrintLoopApi } from './client'

export { ApiError, WrongBackendError } from './client'
export type { PrintLoopApi } from './client'

/** true with `npm run dev:fixtures`: the UI uses the recorded replies, no backend needed. */
export const USE_FIXTURES = import.meta.env.MODE === 'fixtures'

let fixtures: Promise<PrintLoopApi> | null = null
// Dynamic import: the fixtures stay out of the production bundle.
const loadFixtures = () => (fixtures ??= import('./fixtures').then((m) => m.fixtureApi))

function lazy(load: () => Promise<PrintLoopApi>): PrintLoopApi {
  return {
    health: () => load().then((a) => a.health()),
    taxonomy: () => load().then((a) => a.taxonomy()),
    listCases: () => load().then((a) => a.listCases()),
    getCase: (id) => load().then((a) => a.getCase(id)),
    createCase: (project, name) => load().then((a) => a.createCase(project, name)),
    deleteCase: (id) => load().then((a) => a.deleteCase(id)),
    uploadPhotos: (id, photos, note) => load().then((a) => a.uploadPhotos(id, photos, note)),
    diagnose: (id, req) => load().then((a) => a.diagnose(id, req)),
    propose: (id) => load().then((a) => a.propose(id)),
    decide: (id, req) => load().then((a) => a.decide(id, req)),
    confirm: (id, note) => load().then((a) => a.confirm(id, note)),
    rewind: (id, iteration, step) => load().then((a) => a.rewind(id, iteration, step)),
    audit: (id) => load().then((a) => a.audit(id)),
  }
}

export const api: PrintLoopApi = USE_FIXTURES ? lazy(loadFixtures) : httpApi
