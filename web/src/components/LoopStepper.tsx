import type { Case } from '../api/types'
import { STEPS, currentStep } from '../lib/loop'

type Status = 'done' | 'current' | 'todo' | 'stopped'

export function LoopStepper({ data }: { data: Case }) {
  const current = currentStep(data)
  const stopped = data.state === 'escalated'
  const lastIteration = data.iterations[data.iterations.length - 1]
  // In escalation il passo fermo è quello in cui il loop si è interrotto.
  const stopAt = stopped ? (lastIteration?.proposal ? 2 : 1) : -1

  const statusOf = (i: number): Status => {
    if (stopped) return i < stopAt ? 'done' : i === stopAt ? 'stopped' : 'todo'
    if (i < current) return 'done'
    return i === current ? 'current' : 'todo'
  }

  const active = stopped ? stopAt : current
  return (
    <>
      <ol className="stepper" aria-label="Avanzamento del loop">
        {STEPS.map((label, i) => {
          const status = statusOf(i)
          return (
            <li key={label} data-status={status} aria-current={status === 'current' ? 'step' : undefined}>
              <span className="stepper__label">
                {label}
                <span className="sr-only">
                  {status === 'done'
                    ? ' (completato)'
                    : status === 'current'
                      ? ' (in corso)'
                      : status === 'stopped'
                        ? ' (interrotto)'
                        : ''}
                </span>
              </span>
            </li>
          )
        })}
      </ol>
      {active < STEPS.length && (
        <p className="stepper__current" aria-hidden="true">
          Passo {active + 1} di {STEPS.length} · {STEPS[active]}
          {stopped ? ' (interrotto)' : ''}
        </p>
      )}
    </>
  )
}
