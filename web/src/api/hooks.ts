import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '.'
import type { Case, CaseSummary, DecisionRequest, DiagnoseRequest, LiveStartRequest, RewindTarget } from './types'

export const keys = {
  health: ['health'] as const,
  taxonomy: ['taxonomy'] as const,
  cases: ['cases'] as const,
  case: (id: string) => ['case', id] as const,
  audit: (id: string) => ['case', id, 'audit'] as const,
  live: ['live'] as const,
}

export const useHealth = () => useQuery({ queryKey: keys.health, queryFn: () => api.health(), refetchInterval: 30_000 })

export const useTaxonomy = () =>
  useQuery({ queryKey: keys.taxonomy, queryFn: () => api.taxonomy(), staleTime: Infinity })

/** Readable label of a defect code (taxonomy of the backend; the detector's codes are all in it). */
export function useDefectLabel() {
  const { data } = useTaxonomy()
  return (code: string) => (code === 'none' ? 'No defect' : (data?.defects.find((d) => d.id === code)?.label ?? code))
}

export const useCases = () => useQuery({ queryKey: keys.cases, queryFn: () => api.listCases() })

export const useCase = (id: string) => useQuery({ queryKey: keys.case(id), queryFn: () => api.getCase(id) })

export const useAudit = (id: string, enabled: boolean) =>
  useQuery({ queryKey: keys.audit(id), queryFn: () => api.audit(id), enabled })

/** Every mutation returns the updated case: write it to the cache without a second round trip. */
function useCaseMutation<V>(id: string, fn: (vars: V) => Promise<Case>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      qc.setQueryData(keys.case(id), data)
      void qc.invalidateQueries({ queryKey: keys.cases })
      void qc.invalidateQueries({ queryKey: keys.audit(id) })
    },
  })
}

export function useCreateCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ project, name }: { project: File; name: string }) => api.createCase(project, name),
    onSuccess: (data) => {
      qc.setQueryData(keys.case(data.id), data)
      void qc.invalidateQueries({ queryKey: keys.cases })
    },
  })
}

export const useUploadPhotos = (id: string) =>
  useCaseMutation(id, ({ photos, note }: { photos: File[]; note: string }) => api.uploadPhotos(id, photos, note))

export const useDiagnose = (id: string) => useCaseMutation(id, (req: DiagnoseRequest) => api.diagnose(id, req))

export const usePropose = (id: string) => useCaseMutation(id, () => api.propose(id))

export const useDecide = (id: string) => useCaseMutation(id, (req: DecisionRequest) => api.decide(id, req))

export const useRewind = (id: string) =>
  useCaseMutation(id, ({ iteration, step }: Pick<RewindTarget, 'iteration' | 'step'>) =>
    api.rewind(id, iteration, step),
  )

/** Not bound to one case: the case list confirms reprints row by row. */
export function useConfirmSuccess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, note = '' }: { id: string; note?: string }) => api.confirm(id, note),
    onSuccess: (data) => {
      qc.setQueryData(keys.case(data.id), data)
      void qc.invalidateQueries({ queryKey: keys.cases })
      void qc.invalidateQueries({ queryKey: keys.audit(data.id) })
    },
  })
}

export function useDeleteCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.deleteCase(id),
    onSuccess: (_data, id) => {
      qc.setQueryData<CaseSummary[]>(keys.cases, (rows) => rows?.filter((c) => c.id !== id))
      qc.removeQueries({ queryKey: keys.case(id) })
      void qc.invalidateQueries({ queryKey: keys.cases })
    },
  })
}

/** Live session: polled every 2 s while it runs (one frame every few seconds does not need push). */
export const useLive = () =>
  useQuery({
    queryKey: keys.live,
    queryFn: () => api.live(),
    refetchInterval: (q) => (q.state.data?.running ? 2000 : false),
  })

function useLiveMutation<V, R>(fn: (vars: V) => Promise<R>) {
  const qc = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => void qc.invalidateQueries({ queryKey: keys.live }) })
}

export const useLiveStart = () => useLiveMutation((req: LiveStartRequest) => api.liveStart(req))
export const useLiveStop = () => useLiveMutation(() => api.liveStop())
export const useLiveDismiss = () =>
  useLiveMutation(({ id, reason }: { id: string; reason: string }) => api.liveDismiss(id, reason))

export function useLiveAttach() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ caseId, sessionId }: { caseId: string; sessionId?: string }) => api.liveAttach(caseId, sessionId),
    onSuccess: (data) => {
      qc.setQueryData(keys.case(data.id), data)
      void qc.invalidateQueries({ queryKey: keys.cases })
    },
  })
}
