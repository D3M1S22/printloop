import { Link, useParams } from 'react-router'
import { ApiError } from '../api'
import { useCase, useDecide, useDiagnose, usePropose, useUploadPhotos } from '../api/hooks'
import type { Case, DefectClass, Iteration } from '../api/types'
import { DecisionPanel } from '../components/DecisionPanel'
import { DiagnosisView, ManualDiagnosisForm } from '../components/Diagnosis'
import { AuditLog, IterationHistory } from '../components/History'
import { LoopStepper } from '../components/LoopStepper'
import { ChangeList, PatchReview } from '../components/PatchReview'
import { PhotoGrid, PhotoUploader } from '../components/Photos'
import { Badge, Button, Card, ErrorNotice, Notice, Spinner, StateBadge } from '../components/ui'
import { OUTCOME_LABEL, duration, num } from '../lib/format'

function useActions(id: string) {
  const upload = useUploadPhotos(id)
  const diagnose = useDiagnose(id)
  const propose = usePropose(id)
  const decide = useDecide(id)
  const manual = (defect: DefectClass, severity: number, note: string) =>
    diagnose.mutate({ mode: 'operator', defect, severity, note })
  return { upload, diagnose, propose, decide, manual }
}
type Actions = ReturnType<typeof useActions>

const lastOf = (c: Case): Iteration => c.iterations[c.iterations.length - 1]!

function ManualFallback({ actions, initial }: { actions: Actions; initial?: DefectClass }) {
  return (
    <details className="disclosure">
      <summary>Indica il difetto a mano</summary>
      <div>
        <ManualDiagnosisForm onSubmit={actions.manual} busy={actions.diagnose.isPending} initial={initial} />
      </div>
    </details>
  )
}

function PhotosStage({ data, actions }: { data: Case; actions: Actions }) {
  const it = lastOf(data)
  const reprint = it.n > 1
  const previous = data.iterations[data.iterations.length - 2]
  return (
    <>
      {reprint && previous?.proposal && (
        <Card
          title="1. Stampa la patch approvata"
          subtitle="Apri il 3MF in BambuStudio/OrcaSlicer o copialo sulla microSD."
          accent
        >
          <ChangeList proposal={previous.proposal} />
          {data.latest_print_file_url && (
            <div className="btn-row">
              <a className="btn btn--primary" href={data.latest_print_file_url} download>
                Scarica il 3MF da stampare
              </a>
              <span className="muted">tempo stimato {duration(previous.slice?.print_time_s)}</span>
            </div>
          )}
        </Card>
      )}
      <Card
        title={reprint ? '2. Foto della ristampa' : 'Foto del pezzo stampato'}
        subtitle={
          reprint
            ? 'Stessa inquadratura delle foto precedenti: la severità si confronta con la stessa rubrica.'
            : undefined
        }
      >
        <PhotoUploader
          reprint={reprint}
          busy={actions.upload.isPending}
          onSubmit={(photos, note) => actions.upload.mutate({ photos, note })}
        />
        <ErrorNotice error={actions.upload.error} />
        <ManualFallback actions={actions} />
        <ErrorNotice error={actions.diagnose.error} />
      </Card>
    </>
  )
}

function DiagnoseStage({ data, actions }: { data: Case; actions: Actions }) {
  const it = lastOf(data)
  const llm = data.llm_mode === 'llm'
  return (
    <>
      <Card title="Foto" subtitle={it.note ? `Nota: ${it.note}` : undefined}>
        <PhotoGrid urls={it.photo_urls} />
        <details className="disclosure">
          <summary>Sostituisci le foto</summary>
          <div>
            <PhotoUploader
              reprint={it.n > 1}
              busy={actions.upload.isPending}
              onSubmit={(photos, note) => actions.upload.mutate({ photos, note })}
            />
            <ErrorNotice error={actions.upload.error} />
          </div>
        </details>
      </Card>
      <Card title="Diagnosi" accent>
        {data.state === 'needs_info' && (
          <Notice tone="warn" title="Il modello chiede altre informazioni">
            {data.message}
          </Notice>
        )}
        {data.state === 'needs_info' && it.diagnosis && <DiagnosisView diagnosis={it.diagnosis} />}
        {llm ? (
          <>
            <div className="btn-row">
              <Button
                variant="primary"
                busy={actions.diagnose.isPending}
                onClick={() => actions.diagnose.mutate({ mode: 'llm' })}
              >
                Analizza con Gemma 4
              </Button>
              <span className="muted">tassonomia chiusa, severità 0–3, evidenze sulle foto</span>
            </div>
            {actions.diagnose.isPending && (
              <Spinner label="Gemma 4 sta analizzando le foto (può richiedere fino a un minuto)…" />
            )}
            <ManualFallback actions={actions} initial={it.diagnosis?.primary} />
          </>
        ) : (
          <>
            <Notice tone="info">
              LLM non configurato: indica tu il difetto. Patch, slicing e verifica funzionano lo stesso.
            </Notice>
            <ManualDiagnosisForm onSubmit={actions.manual} busy={actions.diagnose.isPending} />
          </>
        )}
        <ErrorNotice error={actions.diagnose.error} />
      </Card>
    </>
  )
}

function ProposeStage({ data, actions }: { data: Case; actions: Actions }) {
  const it = lastOf(data)
  return (
    <>
      <Card title="Diagnosi">
        {it.diagnosis && <DiagnosisView diagnosis={it.diagnosis} />}
        <PhotoGrid urls={it.photo_urls} />
        <ManualFallback actions={actions} initial={it.diagnosis?.primary} />
      </Card>
      <Card
        title="Correzione del preset"
        accent
        subtitle="Il parametro si sceglie tra i candidati della knowledge base; il validatore e il pre-flight sul G-code decidono se la patch passa."
      >
        {data.rejected_keys.length > 0 && (
          <p className="muted">Esclusi perché già rifiutati: {data.rejected_keys.join(', ')}</p>
        )}
        <div className="btn-row">
          <Button variant="primary" busy={actions.propose.isPending} onClick={() => actions.propose.mutate()}>
            Proponi una patch verificata
          </Button>
        </div>
        {actions.propose.isPending && <Spinner label="Patch, slicing e verifica sul G-code in corso…" />}
        <ErrorNotice error={actions.propose.error} />
      </Card>
    </>
  )
}

function ApprovalStage({ data, actions }: { data: Case; actions: Actions }) {
  const it = lastOf(data)
  if (!it.proposal) return null
  return (
    <>
      <Card title="Diagnosi">
        {it.diagnosis && <DiagnosisView diagnosis={it.diagnosis} />}
        <PhotoGrid urls={it.photo_urls} />
      </Card>
      <Card title="Patch da approvare" subtitle={data.message} accent>
        <PatchReview proposal={it.proposal} preflight={it.preflight} validation={it.validation} />
      </Card>
      <Card title="Decisione" subtitle="Niente parte senza la tua approvazione. Ogni scelta resta nell'audit.">
        <DecisionPanel
          key={it.proposal.at}
          options={data.edit_options}
          preflightOk={it.preflight?.ok ?? false}
          busy={actions.decide.isPending}
          error={actions.decide.error}
          onDecide={(req) => actions.decide.mutate(req)}
        />
        {actions.decide.isPending && <Spinner label="Registrazione della decisione…" />}
      </Card>
    </>
  )
}

function ClosedStage({ data }: { data: Case }) {
  const it = lastOf(data)
  const ok = data.state === 'done'
  return (
    <>
      <Notice tone={ok ? 'ok' : 'danger'} title={data.outcome ? OUTCOME_LABEL[data.outcome] : 'Caso chiuso'}>
        {data.message}
      </Notice>
      {it.diagnosis && (
        <Card title={ok ? 'Ultima valutazione' : 'Diagnosi'}>
          <DiagnosisView diagnosis={it.diagnosis} />
          <PhotoGrid urls={it.photo_urls} />
        </Card>
      )}
      {data.latest_print_file_url && (
        <Card title="Preset finale">
          <p className="muted">Il 3MF contiene le impostazioni corrette: salvale come preset utente nello slicer.</p>
          <div className="btn-row">
            <a className="btn" href={data.latest_print_file_url} download>
              Scarica il 3MF finale
            </a>
          </div>
        </Card>
      )}
    </>
  )
}

function Stage({ data }: { data: Case }) {
  const actions = useActions(data.id)
  switch (data.state) {
    case 'awaiting_photos':
      return <PhotosStage data={data} actions={actions} />
    case 'ready':
    case 'needs_info':
      return <DiagnoseStage data={data} actions={actions} />
    case 'diagnosed':
      return <ProposeStage data={data} actions={actions} />
    case 'awaiting_approval':
      return <ApprovalStage data={data} actions={actions} />
    default:
      return <ClosedStage data={data} />
  }
}

function Summary({ data }: { data: Case }) {
  const patches = data.iterations.filter((it) => it.decision?.approved).length
  return (
    <Card title="Riepilogo">
      <dl className="kv">
        <dt>Stampante</dt>
        <dd>{data.printer ?? '—'}</dd>
        <dt>Materiale</dt>
        <dd>{data.material ?? '—'}</dd>
        <dt>Processo</dt>
        <dd>{data.process ?? '—'}</dd>
        <dt>Stampa originale</dt>
        <dd>
          {duration(data.baseline.print_time_s)} · {num(data.baseline.filament_g ?? null, 'g')}
        </dd>
        <dt>Patch approvate</dt>
        <dd>
          {patches} / {data.max_iterations}
        </dd>
      </dl>
    </Card>
  )
}

export function CasePage() {
  const { id = '' } = useParams()
  const { data, isLoading, error } = useCase(id)

  if (isLoading) {
    return (
      <main className="page">
        <Spinner label="Caricamento del caso…" />
      </main>
    )
  }
  if (error || !data) {
    const missing = error instanceof ApiError && error.status === 404
    return (
      <main className="page stack">
        <Link className="back" to="/">
          ← Tutti i casi
        </Link>
        <ErrorNotice
          error={error ?? 'Caso non disponibile'}
          title={missing ? 'Caso non trovato' : 'Errore di caricamento'}
        />
      </main>
    )
  }

  const it = lastOf(data)
  return (
    <main className="page">
      <Link className="back" to="/">
        ← Tutti i casi
      </Link>
      <div className="page-head">
        <div>
          <h1>{data.name}</h1>
          <p className="page-head__meta">
            {data.printer} · {data.material}
          </p>
        </div>
        <div className="btn-row">
          <StateBadge state={data.state} />
          <Badge plain>Iterazione {it.n}</Badge>
        </div>
      </div>
      <LoopStepper data={data} />
      <div className="layout">
        <div className="stack">
          <Stage data={data} />
        </div>
        <aside className="stack" aria-label="Dettagli del caso">
          <Summary data={data} />
          <Card title="Storico">
            <IterationHistory data={data} />
          </Card>
          <AuditLog caseId={data.id} />
        </aside>
      </div>
    </main>
  )
}
