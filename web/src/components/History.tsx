import { useState } from 'react'
import { useAudit } from '../api/hooks'
import type { AuditRow, Case } from '../api/types'
import { SOURCE_LABEL, dateTime, num } from '../lib/format'
import { Spinner } from './ui'

export function IterationHistory({ data }: { data: Case }) {
  return (
    <ol className="timeline" aria-label="Iterazioni">
      {data.iterations.map((it, i) => {
        const current = i === data.iterations.length - 1
        const changes = it.proposal?.changes.filter((c) => !c.companion) ?? []
        return (
          <li key={it.n} data-current={current}>
            <strong>Iterazione {it.n}</strong>
            {it.diagnosis ? (
              <span>
                {it.diagnosis.primary_label}, severità {it.diagnosis.severity}/3
              </span>
            ) : (
              <span className="muted">
                {it.photos.length ? `${it.photos.length} foto, da analizzare` : 'in attesa di foto'}
              </span>
            )}
            {changes.length > 0 && (
              <span className="mono">{changes.map((c) => `${c.key} ${num(c.before)}→${num(c.after)}`).join(', ')}</span>
            )}
            {it.proposal && it.decision?.approved && (
              <span className="muted">
                approvata ({SOURCE_LABEL[it.proposal.source]}){it.decision.edited ? ', valori dell’operatore' : ''}
                {it.decision.override_preflight ? ', pre-flight forzato' : ''}
              </span>
            )}
            {it.rejected.length > 0 && <span className="muted">{it.rejected.length} proposta/e rifiutata/e</span>}
            {it.print_file_url && it.decision?.approved && (
              <a href={it.print_file_url} download>
                Scarica il 3MF stampato
              </a>
            )}
          </li>
        )
      })}
    </ol>
  )
}

const EVENT_LABEL: Record<string, string> = {
  case_created: 'Caso creato, slicing di riferimento',
  photos_added: 'Foto caricate',
  diagnosed: 'Diagnosi',
  needs_info: 'Servono altre informazioni',
  proposed: 'Patch proposta e verificata',
  proposal_rejected: 'Proposta scartata dal sistema',
  proposal_edited: 'Valori modificati dall’operatore',
  approved: 'Patch approvata',
  rejected: 'Patch rifiutata',
  stopped: 'Loop fermato',
  escalated: 'Escalation',
  done: 'Caso chiuso',
  llm_error: 'Errore LLM',
}

function describe(row: AuditRow): string {
  const reason = typeof row.reason === 'string' && row.reason ? `: ${row.reason}` : ''
  return `${EVENT_LABEL[row.event] ?? row.event}${reason}`
}

export function AuditLog({ caseId }: { caseId: string }) {
  const [open, setOpen] = useState(false)
  const { data, isLoading } = useAudit(caseId, open)
  return (
    <details className="disclosure" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Audit log</summary>
      <div>
        {isLoading && <Spinner label="Caricamento…" />}
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
