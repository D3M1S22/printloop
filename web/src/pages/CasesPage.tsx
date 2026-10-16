import { Link, useNavigate } from 'react-router'
import type { CaseState } from '../api/types'
import { useCases, useTaxonomy } from '../api/hooks'
import { NewCaseForm } from '../components/NewCaseForm'
import { Card, ErrorNotice, Spinner, StateBadge } from '../components/ui'
import { OUTCOME_LABEL, dateTime } from '../lib/format'

/** Prossimo passo per l'operatore, mostrato come azione esplicita nella riga. */
const NEXT_ACTION: Record<CaseState, string> = {
  awaiting_photos: 'Carica le foto',
  ready: 'Analizza',
  needs_info: 'Completa la diagnosi',
  diagnosed: 'Proponi la patch',
  awaiting_approval: 'Approva la patch',
  escalated: 'Apri',
  done: 'Apri',
}

function CaseTable() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useCases()
  const { data: taxonomy } = useTaxonomy()
  const label = (id: string | null) => (id ? (taxonomy?.defects.find((d) => d.id === id)?.label ?? id) : '—')

  if (isLoading) return <Spinner label="Caricamento dei casi…" />
  if (error) return <ErrorNotice error={error} title="Casi non disponibili" />
  if (!data || data.length === 0) {
    return <p className="empty">Nessun caso. Carica il progetto 3MF di una stampa venuta male per iniziare.</p>
  }
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Caso</th>
            <th scope="col">Stato</th>
            <th scope="col">Difetto</th>
            <th scope="col">
              <span className="sr-only">Azione</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {data.map((c) => (
            // Tutta la riga è cliccabile; il nome resta un link vero per tastiera e screen reader.
            <tr
              key={c.id}
              className="table__row--link"
              onClick={(e) => {
                if ((e.target as HTMLElement).closest('a')) return
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
                <div className="muted">iterazione {c.iteration}</div>
              </td>
              <td className="table__action">
                <Link
                  to={`/cases/${c.id}`}
                  className={c.state === 'escalated' || c.state === 'done' ? 'btn btn--sm' : 'btn btn--sm btn--primary'}
                  tabIndex={-1}
                  aria-hidden="true"
                >
                  {NEXT_ACTION[c.state]} →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function CasesPage() {
  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>Casi di stampa</h1>
          <p className="page-head__meta">
            Dalla foto di un pezzo difettoso a un preset corretto e verificato sul G-code.
          </p>
        </div>
      </div>
      <div className="layout layout--cases">
        <div className="stack">
          <Card title="Nuovo caso" subtitle="Il progetto 3MF che hai stampato">
            <NewCaseForm />
          </Card>
          <Card title="Come funziona">
            <ol className="how">
              <li>Carichi il 3MF stampato e 1–4 foto del pezzo.</li>
              <li>Gemma 4 su GPU AMD classifica il difetto (o lo indichi tu).</li>
              <li>PrintLoop sceglie al massimo 2 parametri dalla knowledge base e rifà lo slicing.</li>
              <li>Il pre-flight verifica nel G-code che la modifica abbia l'effetto previsto.</li>
              <li>Approvi, rifiuti o correggi i valori; stampi e fotografi la ristampa.</li>
            </ol>
          </Card>
        </div>
        <Card title="Casi">
          <CaseTable />
        </Card>
      </div>
    </main>
  )
}
