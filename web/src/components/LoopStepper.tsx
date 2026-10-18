import type { Case, RewindTarget } from '../api/types'
import { STEPS, currentStep, describeTarget, stepTarget } from '../lib/loop'

type Status = 'done' | 'current' | 'todo' | 'stopped'

const STATUS_TEXT: Record<Status, string> = {
  done: ' (completed)',
  current: ' (in progress)',
  stopped: ' (interrupted)',
  todo: '',
}

/** Loop progress. Completed steps the backend can return to are buttons: `onRewind` asks for confirmation. */
export function LoopStepper({ data, onRewind }: { data: Case; onRewind?: (target: RewindTarget) => void }) {
  const current = currentStep(data)
  const stopped = data.state === 'escalated'
  const lastIteration = data.iterations[data.iterations.length - 1]
  // When escalated, the stopped step is the one where the loop was interrupted.
  const stopAt = stopped ? (lastIteration?.proposal ? 2 : 1) : -1

  const statusOf = (i: number): Status => {
    if (stopped) return i < stopAt ? 'done' : i === stopAt ? 'stopped' : 'todo'
    if (i < current) return 'done'
    return i === current ? 'current' : 'todo'
  }

  const active = stopped ? stopAt : current
  return (
    <>
      <ol className="stepper" aria-label="Loop progress">
        {STEPS.map((label, i) => {
          const status = statusOf(i)
          const target = status !== 'todo' && status !== 'current' && onRewind ? stepTarget(data, i) : undefined
          const text = (
            <span className="stepper__label">
              {label}
              <span className="sr-only">{STATUS_TEXT[status]}</span>
            </span>
          )
          return (
            <li key={label} data-status={status} aria-current={status === 'current' ? 'step' : undefined}>
              {target ? (
                <button
                  type="button"
                  className="stepper__btn"
                  title={`Go back to the ${describeTarget(target)}`}
                  onClick={() => onRewind?.(target)}
                >
                  {text}
                </button>
              ) : (
                text
              )}
            </li>
          )
        })}
      </ol>
      {active < STEPS.length && (
        <p className="stepper__current" aria-hidden="true">
          Step {active + 1} of {STEPS.length} · {STEPS[active]}
          {stopped ? ' (interrupted)' : ''}
        </p>
      )}
    </>
  )
}
