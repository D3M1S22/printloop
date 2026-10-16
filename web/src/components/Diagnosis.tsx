import { useId, useState } from 'react'
import { useTaxonomy } from '../api/hooks'
import type { DefectClass, Diagnosis } from '../api/types'
import { SEVERITY_LABEL, percent } from '../lib/format'
import { Badge, Button, Severity } from './ui'

const fileName = (path: string) => path.split('/').pop() ?? path

export function DiagnosisView({ diagnosis }: { diagnosis: Diagnosis }) {
  const { data: taxonomy } = useTaxonomy()
  const labelOf = (id: DefectClass) => taxonomy?.defects.find((d) => d.id === id)?.label ?? id
  const primary = diagnosis.findings.find((f) => f.defect === diagnosis.primary)
  const others = diagnosis.findings.filter((f) => f.defect !== diagnosis.primary)
  const fromModel = diagnosis.source === 'llm'
  return (
    <div className="diagnosis">
      <div className="diagnosis__title">
        <strong>{diagnosis.primary_label}</strong>
        <Severity level={diagnosis.severity} />
        <span className="muted">
          severità {diagnosis.severity}/3, {SEVERITY_LABEL[diagnosis.severity] ?? ''}
        </span>
      </div>
      <div className="btn-row">
        <Badge tone={fromModel ? 'info' : 'neutral'} plain>
          {fromModel ? `Gemma 4 · ${diagnosis.model ?? 'LLM'}` : 'Indicata dall’operatore'}
        </Badge>
        {fromModel && <Badge plain>confidenza {percent(diagnosis.confidence)}</Badge>}
        {fromModel && diagnosis.latency_ms !== null && <Badge plain>{Math.round(diagnosis.latency_ms)} ms</Badge>}
      </div>
      {primary && primary.evidence.length > 0 && fromModel && (
        <ul className="evidence" aria-label="Evidenze">
          {primary.evidence.map((e, i) => (
            <li key={i}>
              <span className="mono">{fileName(e.photo)}</span>: {e.description}
            </li>
          ))}
        </ul>
      )}
      {primary?.location && <p className="muted">Dove: {primary.location}</p>}
      {others.length > 0 && (
        <p className="muted">
          Altri difetti visti: {others.map((f) => `${labelOf(f.defect)} (${f.severity}/3)`).join(', ')}
        </p>
      )}
      {diagnosis.note && <p className="muted">Nota: {diagnosis.note}</p>}
    </div>
  )
}

/** Diagnosi dell'operatore: percorso offline e correzione umana di quella del modello. */
export function ManualDiagnosisForm({
  onSubmit,
  busy,
  initial,
}: {
  onSubmit: (defect: DefectClass, severity: number, note: string) => void
  busy: boolean
  initial?: DefectClass
}) {
  const { data } = useTaxonomy()
  const selectId = useId()
  const noteId = useId()
  const [defect, setDefect] = useState<DefectClass | ''>(initial ?? '')
  const [severity, setSeverity] = useState(2)
  const [note, setNote] = useState('')
  const options = data?.defects.filter((d) => d.id !== 'other') ?? []
  const selected = options.find((d) => d.id === defect)

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault()
        if (defect) onSubmit(defect, severity, note)
      }}
    >
      <div className="field">
        <label htmlFor={selectId}>Difetto osservato</label>
        <select id={selectId} value={defect} onChange={(e) => setDefect(e.target.value as DefectClass)} required>
          <option value="" disabled>
            Scegli…
          </option>
          {options.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
              {d.fixable ? '' : ' (non correggibile dal preset)'}
            </option>
          ))}
        </select>
        {selected && <span className="hint">{selected.description}</span>}
      </div>
      {defect !== 'none' && (
        <fieldset className="field">
          <legend>Severità</legend>
          <div className="segmented" role="radiogroup">
            {[1, 2, 3].map((level) => (
              <label key={level}>
                <input
                  type="radio"
                  name="severity"
                  value={level}
                  checked={severity === level}
                  onChange={() => setSeverity(level)}
                />
                {level} · {SEVERITY_LABEL[level]}
              </label>
            ))}
          </div>
          <span className="hint">1 = solo estetico, il pezzo è accettabile e il loop si chiude.</span>
        </fieldset>
      )}
      <div className="field">
        <label htmlFor={noteId}>Nota (facoltativa)</label>
        <textarea id={noteId} value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      <div className="btn-row">
        <Button type="submit" variant="primary" busy={busy} disabled={!defect}>
          Conferma la diagnosi
        </Button>
      </div>
    </form>
  )
}
