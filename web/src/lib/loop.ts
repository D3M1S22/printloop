import type { Case } from '../api/types'

export const STEPS = ['Foto', 'Diagnosi', 'Patch verificata', 'Approvazione', 'Ristampa'] as const

/** Indice del passo corrente del loop, dato lo stato del caso. */
export function currentStep(c: Case): number {
  const n = c.iterations.length
  switch (c.state) {
    case 'awaiting_photos':
      return n > 1 ? 4 : 0
    case 'ready':
    case 'needs_info':
      return 1
    case 'diagnosed':
      return 2
    case 'awaiting_approval':
      return 3
    default:
      return STEPS.length
  }
}
