import { Link, useNavigate } from 'react-router'
import type { CaseState } from '../api/types'
import { useCases, useConfirmSuccess, useDeleteCase, useTaxonomy } from '../api/hooks'
import { NewCaseForm } from '../components/NewCaseForm'
import { Button, Card, ConfirmButton, ErrorNotice, Spinner, StateBadge } from '../components/ui'
import { OUTCOME_LABEL, dateTime } from '../lib/format'

/** Next step for the operator, shown as an explicit action in the row. */
const NEXT_ACTION: Record<CaseState, string> = {
  awaiting_photos: 'Upload photos',
  ready: 'Analyse',
  needs_info: 'Complete the diagnosis',
  diagnosed: 'Propose the patch',
  awaiting_approval: 'Approve the patch',
  escalated: 'Open',
  done: 'Open',
}

function CaseTable() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useCases()
  const { data: taxonomy } = useTaxonomy()
  const confirm = useConfirmSuccess()
  const remove = useDeleteCase()
  const label = (id: string | null) => (id ? (taxonomy?.defects.find((d) => d.id === id)?.label ?? id) : '—')

  if (isLoading) return <Spinner label="Loading the cases…" />
  if (error) return <ErrorNotice error={error} title="Cases unavailable" />
  if (!data || data.length === 0) {
    return <p className="empty">No cases yet. Upload the 3MF project of a print that came out wrong to start.</p>
  }
  // No wrapping grid here: .table-wrap must stay a direct child of the card body to scroll on small screens.
  return (
    <>
      <ErrorNotice error={confirm.error} title="Reprint not confirmed" />
      <ErrorNotice error={remove.error} title="Case not deleted" />
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Case</th>
              <th scope="col">State</th>
              <th scope="col">Defect</th>
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {data.map((c) => (
              // The whole row is clickable; the name stays a real link for keyboard and screen reader users.
              <tr
                key={c.id}
                className="table__row--link"
                onClick={(e) => {
                  if ((e.target as HTMLElement).closest('a, button')) return
                  if (window.getSelection()?.toString()) return
                  navigate(`/cases/${c.id}`)
                }}
              >
                <td>
                  <Link to={`/cases/${c.id}`}>{c.name}</Link>
                  <div className="muted">
                    {c.material} · {c.printer}
                  </div>
                </td>
                <td>
                  <StateBadge state={c.state} />
                  <div className="muted">
                    {c.outcome ? `${OUTCOME_LABEL[c.outcome]} · ` : ''}
                    {dateTime(c.updated_at)}
                  </div>
                </td>
                <td>
                  {label(c.defect)}
                  <div className="muted">iteration {c.iteration}</div>
                </td>
                <td className="table__action">
                  <div className="btn-row">
                    {c.allowed_actions.includes('confirm_success') && (
                      <Button
                        size="sm"
                        variant="ok"
                        title="The reprint is good: close the case as fixed"
                        busy={confirm.isPending && confirm.variables?.id === c.id}
                        onClick={() => confirm.mutate({ id: c.id })}
                      >
                        ✓ Reprint OK
                      </Button>
                    )}
                    <Link
                      to={`/cases/${c.id}`}
                      className={
                        c.state === 'escalated' || c.state === 'done' ? 'btn btn--sm' : 'btn btn--sm btn--primary'
                      }
                      tabIndex={-1}
                      aria-hidden="true"
                    >
                      {NEXT_ACTION[c.state]} →
                    </Link>
                    <ConfirmButton
                      size="sm"
                      question={`Delete “${c.name}” and all its files?`}
                      confirmLabel="Delete"
                      busy={remove.isPending && remove.variables === c.id}
                      onConfirm={() => remove.mutate(c.id)}
                    >
                      Delete
                    </ConfirmButton>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

export function CasesPage() {
  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>Print cases</h1>
          <p className="page-head__meta">
            From a photo of a defective part to a corrected preset verified on the G-code.
          </p>
        </div>
      </div>
      <div className="layout layout--cases">
        <div className="stack">
          <Card title="New case" subtitle="The 3MF project you printed">
            <NewCaseForm />
          </Card>
          <Card title="How it works">
            <ol className="how">
              <li>Upload the printed 3MF and 1–4 photos of the part.</li>
              <li>Gemma 4 on an AMD GPU classifies the defect (or you state it).</li>
              <li>PrintLoop picks at most 2 parameters from the knowledge base and re-slices.</li>
              <li>The pre-flight checks in the G-code that the change has the expected effect.</li>
              <li>
                You approve, reject or adjust the values, then print: if the reprint is good, one click closes the case.
              </li>
            </ol>
          </Card>
        </div>
        <Card title="Cases">
          <CaseTable />
        </Card>
      </div>
    </main>
  )
}
