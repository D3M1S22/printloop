import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError } from '../api'
import {
  useCase,
  useConfirmSuccess,
  useDefectLabel,
  useDecide,
  useDeleteCase,
  useDiagnose,
  usePropose,
  useRewind,
  useUploadPhotos,
} from '../api/hooks'
import type { Case, DefectClass, Iteration, RewindTarget } from '../api/types'
import { DecisionPanel } from '../components/DecisionPanel'
import { DiagnosisView, ManualDiagnosisForm } from '../components/Diagnosis'
import { AuditLog, IterationHistory } from '../components/History'
import { LoopStepper } from '../components/LoopStepper'
import { ChangeList, PatchReview } from '../components/PatchReview'
import { PhotoGrid, PhotoUploader } from '../components/Photos'
import { Badge, Button, Card, ConfirmButton, ErrorNotice, Notice, Spinner, StateBadge } from '../components/ui'
import { OUTCOME_LABEL, duration, num } from '../lib/format'
import { describeTarget, previousStep } from '../lib/loop'

function useActions(id: string) {
  const upload = useUploadPhotos(id)
  const diagnose = useDiagnose(id)
  const propose = usePropose(id)
  const decide = useDecide(id)
  const confirm = useConfirmSuccess()
  const manual = (defect: DefectClass, severity: number, note: string) =>
    diagnose.mutate({ mode: 'operator', defect, severity, note })
  return { upload, diagnose, propose, decide, confirm, manual }
}
type Actions = ReturnType<typeof useActions>

const lastOf = (c: Case): Iteration => c.iterations[c.iterations.length - 1]!

/** "a", "a and b", "a, b and c". */
function listOf(items: string[]): string {
  if (items.length < 2) return items.join('')
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

/** Detector labels under each photo ("E4B: stringing"), when the detector ran on them. */
function useCaptions(it: Iteration): (string | undefined)[] {
  const label = useDefectLabel()
  return it.photos.map((photo) => {
    const det = it.detections?.find((d) => d.photo === photo)
    if (!det) return undefined
    if (det.error) return 'E4B: no answer'
    return `E4B: ${det.defects.length ? det.defects.map(label).join(', ') : 'no defect'}`
  })
}

/** Union of the detector's classes over the photos, in its urgency order (the backend already sorts each photo). */
const detectedClasses = (it: Iteration): string[] => [
  ...new Set((it.detections ?? []).filter((d) => !d.error).flatMap((d) => d.defects)),
]

function ManualFallback({
  actions,
  initial,
  suggestions,
  open,
}: {
  actions: Actions
  initial?: DefectClass
  suggestions?: string[]
  open?: boolean
}) {
  return (
    <details className="disclosure" open={open}>
      <summary>State the defect manually</summary>
      <div>
        <ManualDiagnosisForm
          onSubmit={actions.manual}
          busy={actions.diagnose.isPending}
          initial={initial}
          suggestions={suggestions}
        />
      </div>
    </details>
  )
}

/** After an approved patch: if the reprint is good, one click closes the case (it can be undone with "Step back"). */
function ReprintCheck({ data, actions, title }: { data: Case; actions: Actions; title: string }) {
  if (!data.allowed_actions.includes('confirm_success')) return null
  return (
    <Card
      title={title}
      subtitle="If the defect is gone, close the case now. Otherwise upload photos of the reprint for another iteration."
    >
      <div className="btn-row">
        <Button variant="ok" busy={actions.confirm.isPending} onClick={() => actions.confirm.mutate({ id: data.id })}>
          ✓ Reprint OK, close the case
        </Button>
      </div>
      <ErrorNotice error={actions.confirm.error} title="Reprint not confirmed" />
    </Card>
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
          title="1. Print the approved patch"
          subtitle="Open the 3MF in BambuStudio/OrcaSlicer or copy it to the microSD card."
          accent
        >
          <ChangeList proposal={previous.proposal} />
          {data.latest_print_file_url && (
            <div className="btn-row">
              <a className="btn btn--primary" href={data.latest_print_file_url} download>
                Download the 3MF to print
              </a>
              <span className="muted">estimated time {duration(previous.slice?.print_time_s)}</span>
            </div>
          )}
        </Card>
      )}
      {reprint && <ReprintCheck data={data} actions={actions} title="2. Is the reprint good?" />}
      <Card
        title={reprint ? '3. Photos of the reprint' : 'Photos of the printed part'}
        subtitle={
          reprint
            ? 'Only if the defect is still there. Same framing as the previous photos: severity is compared with the same rubric.'
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
  const captions = useCaptions(it)
  const detected = detectedClasses(it)
  const disagree = data.state === 'needs_info' && it.diagnosis?.detector?.agreement === 'disagree'
  const suggestions = [...new Set([...detected, ...(it.diagnosis ? [it.diagnosis.primary] : [])])].filter(
    (d) => d !== 'none',
  )
  return (
    <>
      <ReprintCheck data={data} actions={actions} title="Is the reprint good?" />
      <Card title="Photos" subtitle={it.note ? `Note: ${it.note}` : undefined}>
        <PhotoGrid urls={it.photo_urls} captions={captions} />
        <details className="disclosure">
          <summary>Replace the photos</summary>
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
      <Card title="Diagnosis" accent>
        {data.state === 'needs_info' && (
          <Notice
            tone="warn"
            title={disagree ? 'The detector and the model disagree' : 'The model asks for more information'}
          >
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
                Analyse with Gemma 4
              </Button>
              <span className="muted">closed taxonomy, severity 0–3, evidence on the photos</span>
            </div>
            {actions.diagnose.isPending && (
              <Spinner label="Gemma 4 is analysing the photos (this can take up to a minute)…" />
            )}
            <ManualFallback
              actions={actions}
              initial={it.diagnosis?.primary}
              suggestions={suggestions}
              open={disagree}
            />
          </>
        ) : (
          <>
            <Notice tone="info">
              {detected.length || it.detections?.length
                ? 'The 26B is not configured: the defect is pre-filled from the detector, set the severity and confirm.'
                : 'LLM not configured: state the defect yourself. Patch, slicing and verification work all the same.'}
            </Notice>
            <ManualDiagnosisForm
              onSubmit={actions.manual}
              busy={actions.diagnose.isPending}
              initial={detected[0] as DefectClass | undefined}
              suggestions={detected}
            />
          </>
        )}
        <ErrorNotice error={actions.diagnose.error} />
      </Card>
    </>
  )
}

function ProposeStage({ data, actions }: { data: Case; actions: Actions }) {
  const it = lastOf(data)
  const captions = useCaptions(it)
  return (
    <>
      <ReprintCheck data={data} actions={actions} title="Is the reprint good after all?" />
      <Card title="Diagnosis">
        {it.diagnosis && <DiagnosisView diagnosis={it.diagnosis} />}
        <PhotoGrid urls={it.photo_urls} captions={captions} />
        <ManualFallback actions={actions} initial={it.diagnosis?.primary} />
      </Card>
      <Card
        title="Preset correction"
        accent
        subtitle="The parameter is chosen among the knowledge base candidates; the validator and the G-code pre-flight decide whether the patch passes."
      >
        {data.rejected_keys.length > 0 && (
          <p className="muted">Excluded because already rejected: {data.rejected_keys.join(', ')}</p>
        )}
        <div className="btn-row">
          <Button variant="primary" busy={actions.propose.isPending} onClick={() => actions.propose.mutate()}>
            Propose a verified patch
          </Button>
        </div>
        {actions.propose.isPending && <Spinner label="Patch, slicing and G-code verification in progress…" />}
        <ErrorNotice error={actions.propose.error} />
      </Card>
    </>
  )
}

function ApprovalStage({ data, actions }: { data: Case; actions: Actions }) {
  const it = lastOf(data)
  const captions = useCaptions(it)
  if (!it.proposal) return null
  return (
    <>
      <Card title="Diagnosis">
        {it.diagnosis && <DiagnosisView diagnosis={it.diagnosis} />}
        <PhotoGrid urls={it.photo_urls} captions={captions} />
      </Card>
      <Card title="Patch to approve" subtitle={data.message} accent>
        <PatchReview proposal={it.proposal} preflight={it.preflight} validation={it.validation} />
      </Card>
      <Card title="Decision" subtitle="Nothing ships without your approval. Every choice is kept in the audit log.">
        <DecisionPanel
          key={it.proposal.at}
          options={data.edit_options}
          preflightOk={it.preflight?.ok ?? false}
          busy={actions.decide.isPending}
          error={actions.decide.error}
          onDecide={(req) => actions.decide.mutate(req)}
        />
        {actions.decide.isPending && <Spinner label="Recording the decision…" />}
      </Card>
    </>
  )
}

function ClosedStage({ data }: { data: Case }) {
  const it = lastOf(data)
  const captions = useCaptions(it)
  const ok = data.state === 'done'
  return (
    <>
      <Notice tone={ok ? 'ok' : 'danger'} title={data.outcome ? OUTCOME_LABEL[data.outcome] : 'Case closed'}>
        {data.message}
      </Notice>
      {it.diagnosis && (
        <Card title={ok ? 'Last assessment' : 'Diagnosis'}>
          <DiagnosisView diagnosis={it.diagnosis} />
          <PhotoGrid urls={it.photo_urls} captions={captions} />
        </Card>
      )}
      {data.latest_print_file_url && (
        <Card title="Final preset">
          <p className="muted">The 3MF holds the corrected settings: save them as a user preset in the slicer.</p>
          <div className="btn-row">
            <a className="btn" href={data.latest_print_file_url} download>
              Download the final 3MF
            </a>
          </div>
        </Card>
      )}
    </>
  )
}

function Stage({ data, actions }: { data: Case; actions: Actions }) {
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

/** Confirmation for going back: says what is discarded before doing it. */
function RewindPanel({
  target,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  target: RewindTarget
  busy: boolean
  error: unknown
  onConfirm: () => void
  onCancel: () => void
}) {
  const confirmRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    confirmRef.current?.focus()
    confirmRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [target])
  return (
    <div className="notice notice--warn rewind-panel" role="group" aria-label="Go back">
      <strong>Go back to the {describeTarget(target)}?</strong>
      <span>
        {target.discards.length ? `This discards ${listOf(target.discards)}.` : 'Nothing is discarded.'} Photos and
        files are archived in the case folder, not deleted.
      </span>
      <div className="btn-row">
        <Button ref={confirmRef} variant="primary" busy={busy} onClick={onConfirm}>
          Go back
        </Button>
        <Button variant="ghost" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
      <ErrorNotice error={error} title="Could not go back" />
    </div>
  )
}

function Summary({ data }: { data: Case }) {
  const patches = data.iterations.filter((it) => it.decision?.approved).length
  return (
    <Card title="Summary">
      <dl className="kv">
        <dt>Printer</dt>
        <dd>{data.printer ?? '—'}</dd>
        <dt>Material</dt>
        <dd>{data.material ?? '—'}</dd>
        <dt>Process</dt>
        <dd>{data.process ?? '—'}</dd>
        <dt>Original print</dt>
        <dd>
          {duration(data.baseline.print_time_s)} · {num(data.baseline.filament_g ?? null, 'g')}
        </dd>
        <dt>Slicer</dt>
        <dd>{data.baseline.slicer ?? '—'}</dd>
        <dt>Approved patches</dt>
        <dd>
          {patches} / {data.max_iterations}
        </dd>
      </dl>
      {data.baseline.notes?.map((note) => (
        <Notice key={note} tone="warn">
          {note}
        </Notice>
      ))}
    </Card>
  )
}

function CaseView({ data }: { data: Case }) {
  const navigate = useNavigate()
  const actions = useActions(data.id)
  const rewind = useRewind(data.id)
  const remove = useDeleteCase()
  const [pending, setPending] = useState<RewindTarget | null>(null)
  const it = lastOf(data)
  const back = previousStep(data)

  const ask = (target: RewindTarget) => {
    rewind.reset()
    setPending(target)
  }
  const goBack = (target: RewindTarget) =>
    rewind.mutate({ iteration: target.iteration, step: target.step }, { onSuccess: () => setPending(null) })

  return (
    <main className="page">
      <Link className="back" to="/">
        ← All cases
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
          <Badge plain>Iteration {it.n}</Badge>
          {back && (
            <Button size="sm" title={`Go back to the ${describeTarget(back)}`} onClick={() => ask(back)}>
              ↶ Step back
            </Button>
          )}
          <ConfirmButton
            size="sm"
            question="Delete this case and all its files?"
            confirmLabel="Delete"
            busy={remove.isPending}
            onConfirm={() => remove.mutate(data.id, { onSuccess: () => void navigate('/') })}
          >
            Delete case
          </ConfirmButton>
        </div>
      </div>
      <ErrorNotice error={remove.error} title="Case not deleted" />
      <LoopStepper data={data} onRewind={ask} />
      {pending && (
        <RewindPanel
          target={pending}
          busy={rewind.isPending}
          error={rewind.error}
          onConfirm={() => goBack(pending)}
          onCancel={() => setPending(null)}
        />
      )}
      <div className="layout">
        <div className="stack">
          <Stage data={data} actions={actions} />
        </div>
        <aside className="stack" aria-label="Case details">
          <Summary data={data} />
          <Card title="History">
            <IterationHistory data={data} onRewind={ask} />
          </Card>
          <AuditLog caseId={data.id} />
        </aside>
      </div>
    </main>
  )
}

export function CasePage() {
  const { id = '' } = useParams()
  const { data, isLoading, error } = useCase(id)

  if (isLoading) {
    return (
      <main className="page">
        <Spinner label="Loading the case…" />
      </main>
    )
  }
  if (error || !data) {
    const missing = error instanceof ApiError && error.status === 404
    return (
      <main className="page stack">
        <Link className="back" to="/">
          ← All cases
        </Link>
        <ErrorNotice error={error ?? 'Case unavailable'} title={missing ? 'Case not found' : 'Loading error'} />
      </main>
    )
  }
  return <CaseView data={data} />
}
