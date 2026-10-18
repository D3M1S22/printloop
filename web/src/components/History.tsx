import { useState } from 'react'
import { useAudit } from '../api/hooks'
import type { AuditRow, Case, RewindStep, RewindTarget } from '../api/types'
import { SOURCE_LABEL, dateTime, num } from '../lib/format'
import { REWIND_STEP_LABEL, iterationTarget } from '../lib/loop'
import { Button, Spinner } from './ui'

const plural = (n: number, noun: string) => `${n} ${noun}${n === 1 ? '' : 's'}`

export function IterationHistory({ data, onRewind }: { data: Case; onRewind?: (target: RewindTarget) => void }) {
  return (
    <ol className="timeline" aria-label="Iterations">
      {data.iterations.map((it, i) => {
        const current = i === data.iterations.length - 1
        const changes = it.proposal?.changes.filter((c) => !c.companion) ?? []
        const target = !current && onRewind ? iterationTarget(data, it.n) : undefined
        return (
          <li key={it.n} data-current={current}>
            <strong>Iteration {it.n}</strong>
            {it.diagnosis ? (
              <span>
                {it.diagnosis.primary_label}, severity {it.diagnosis.severity}/3
              </span>
            ) : (
              <span className="muted">
                {it.photos.length ? `${plural(it.photos.length, 'photo')}, not analysed yet` : 'awaiting photos'}
              </span>
            )}
            {changes.length > 0 && (
              <span className="mono">{changes.map((c) => `${c.key} ${num(c.before)}→${num(c.after)}`).join(', ')}</span>
            )}
            {it.proposal && it.decision?.approved && (
              <span className="muted">
                approved ({SOURCE_LABEL[it.proposal.source]}){it.decision.edited ? ', operator values' : ''}
                {it.decision.override_preflight ? ', pre-flight overridden' : ''}
              </span>
            )}
            {it.rejected.length > 0 && <span className="muted">{plural(it.rejected.length, 'rejected proposal')}</span>}
            {it.confirmed && <span className="muted">reprint confirmed good by the {it.confirmed.actor}</span>}
            {it.print_file_url && it.decision?.approved && (
              <a href={it.print_file_url} download>
                Download the printed 3MF
              </a>
            )}
            {target && (
              <div>
                <Button
                  size="sm"
                  variant="ghost"
                  title={`Reopen the ${REWIND_STEP_LABEL[target.step]} of iteration ${it.n}`}
                  onClick={() => onRewind?.(target)}
                >
                  ↶ Back to this iteration
                </Button>
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}

const EVENT_LABEL: Record<string, string> = {
  case_created: 'Case created, reference slice',
  photos_added: 'Photos uploaded',
  diagnosed: 'Diagnosis',
  needs_info: 'More information needed',
  proposed: 'Patch proposed and verified',
  proposal_rejected: 'Proposal discarded by the system',
  proposal_edited: 'Values edited by the operator',
  approved: 'Patch approved',
  rejected: 'Patch rejected',
  stopped: 'Loop stopped',
  escalated: 'Escalated',
  done: 'Case closed',
  confirmed_success: 'Reprint confirmed good',
  rewound: 'Went back',
  llm_error: 'LLM error',
}

function describe(row: AuditRow): string {
  if (row.event === 'rewound' && row.to && typeof row.to === 'object') {
    const to = row.to as { iteration: number; step: RewindStep }
    return `Went back to the ${REWIND_STEP_LABEL[to.step]} of iteration ${to.iteration}`
  }
  const reason = typeof row.reason === 'string' && row.reason ? `: ${row.reason}` : ''
  const note = typeof row.note === 'string' && row.note && row.event === 'confirmed_success' ? `: ${row.note}` : ''
  return `${EVENT_LABEL[row.event] ?? row.event}${reason}${note}`
}

export function AuditLog({ caseId }: { caseId: string }) {
  const [open, setOpen] = useState(false)
  const { data, isLoading } = useAudit(caseId, open)
  return (
    <details className="disclosure" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Audit log</summary>
      <div>
        {isLoading && <Spinner label="Loading…" />}
        {data && (
          <ol className="audit">
            {data.map((row, i) => (
              <li key={i}>
                <time dateTime={row.ts}>{dateTime(row.ts)}</time>
                <span>
                  {describe(row)} <span className="muted">· {row.actor}</span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </details>
  )
}
