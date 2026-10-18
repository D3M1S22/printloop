import type { Case, RewindStep, RewindTarget } from '../api/types'

export const STEPS = ['Photos', 'Diagnosis', 'Verified patch', 'Approval', 'Reprint'] as const

/** Backend step behind the first four stepper columns ("Reprint" is the next iteration's photos). */
const STEP_KEYS: RewindStep[] = ['photos', 'diagnosis', 'patch', 'approval']

export const REWIND_STEP_LABEL: Record<RewindStep, string> = {
  photos: 'photos',
  diagnosis: 'diagnosis',
  patch: 'patch proposal',
  approval: 'approval',
}

/** Index of the current loop step, given the case state. */
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

/**
 * Rewind target behind stepper column `index`, if the backend allows going back there.
 * While waiting for the reprint photos the first four columns show the previous iteration.
 */
export function stepTarget(c: Case, index: number): RewindTarget | undefined {
  const step = STEP_KEYS[index]
  if (!step) return undefined
  const n = c.iterations.length
  const iteration = c.state === 'awaiting_photos' && n > 1 ? n - 1 : n
  return c.rewind_targets.find((t) => t.iteration === iteration && t.step === step)
}

/** "One step back": the latest step the case can return to. */
export const previousStep = (c: Case): RewindTarget | undefined => c.rewind_targets[c.rewind_targets.length - 1]

/** Latest step of an earlier iteration the case can return to (usually its approval). */
export const iterationTarget = (c: Case, iteration: number): RewindTarget | undefined =>
  c.rewind_targets.filter((t) => t.iteration === iteration).pop()

export const describeTarget = (t: RewindTarget): string => `${REWIND_STEP_LABEL[t.step]} of iteration ${t.iteration}`
