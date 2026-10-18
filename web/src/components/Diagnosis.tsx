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
          severity {diagnosis.severity}/3, {SEVERITY_LABEL[diagnosis.severity] ?? ''}
        </span>
      </div>
      <div className="btn-row">
        <Badge tone={fromModel ? 'info' : 'neutral'} plain>
          {fromModel ? `Gemma 4 · ${diagnosis.model ?? 'LLM'}` : 'Stated by the operator'}
        </Badge>
        {fromModel && <Badge plain>confidence {percent(diagnosis.confidence)}</Badge>}
        {fromModel && diagnosis.latency_ms !== null && <Badge plain>{Math.round(diagnosis.latency_ms)} ms</Badge>}
      </div>
      {primary && primary.evidence.length > 0 && fromModel && (
        <ul className="evidence" aria-label="Evidence">
          {primary.evidence.map((e, i) => (
            <li key={i}>
              <span className="mono">{fileName(e.photo)}</span>: {e.description}
            </li>
          ))}
        </ul>
      )}
      {primary?.location && <p className="muted">Where: {primary.location}</p>}
      {others.length > 0 && (
        <p className="muted">
          Other defects seen: {others.map((f) => `${labelOf(f.defect)} (${f.severity}/3)`).join(', ')}
        </p>
      )}
      {diagnosis.note && <p className="muted">Note: {diagnosis.note}</p>}
    </div>
  )
}

/**
 * Operator diagnosis: the offline path and the human correction of the model's one.
 * "No defect" is not offered: a good reprint is closed with "Reprint OK", not by diagnosing nothing.
 */
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
  const [defect, setDefect] = useState<DefectClass | ''>(
    initial && initial !== 'none' && initial !== 'other' ? initial : '',
  )
  const [severity, setSeverity] = useState(2)
  const [note, setNote] = useState('')
  const options = data?.defects.filter((d) => d.id !== 'other' && d.id !== 'none') ?? []
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
        <label htmlFor={selectId}>Observed defect</label>
        <select id={selectId} value={defect} onChange={(e) => setDefect(e.target.value as DefectClass)} required>
          <option value="" disabled>
            Choose…
          </option>
          {options.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
              {d.fixable ? '' : ' (not fixable from the preset)'}
            </option>
          ))}
        </select>
        {selected && <span className="hint">{selected.description}</span>}
      </div>
      <fieldset className="field">
        <legend>Severity</legend>
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
        <span className="hint">1 = cosmetic only: the part is acceptable and the case closes.</span>
      </fieldset>
      <div className="field">
        <label htmlFor={noteId}>Note (optional)</label>
        <textarea id={noteId} value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      <div className="btn-row">
        <Button type="submit" variant="primary" busy={busy} disabled={!defect}>
          Confirm the diagnosis
        </Button>
      </div>
    </form>
  )
}
