import { useId, useState } from 'react'
import { useDefectLabel, useTaxonomy } from '../api/hooks'
import type { DefectClass, DetectorSummary, Diagnosis } from '../api/types'
import { SEVERITY_LABEL, percent } from '../lib/format'
import { Badge, Button, Severity } from './ui'

const fileName = (path: string) => path.split('/').pop() ?? path

const AGREEMENT = {
  agree: { tone: 'ok', text: 'agrees' },
  disagree: { tone: 'warn', text: 'disagrees' },
  unavailable: { tone: 'neutral', text: 'unavailable' },
} as const

/** What the fine-tuned E4B saw on the photos, and whether the diagnosis agrees with it. */
export function DetectorLine({ detector }: { detector: DetectorSummary }) {
  const label = useDefectLabel()
  const a = AGREEMENT[detector.agreement]
  return (
    <p className="btn-row">
      <span className="muted">Detector (fine-tuned E4B):</span>
      <span>
        {detector.agreement === 'unavailable'
          ? 'no answer'
          : detector.defects.length
            ? detector.defects.map(label).join(', ')
            : 'no defect'}
      </span>
      <Badge tone={a.tone} plain>
        {a.text}
      </Badge>
    </p>
  )
}

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
      {diagnosis.detector && <DetectorLine detector={diagnosis.detector} />}
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
  suggestions = [],
}: {
  onSubmit: (defect: DefectClass, severity: number, note: string) => void
  busy: boolean
  initial?: DefectClass
  /** One-click candidates, e.g. what the detector and the model reported when they disagree. */
  suggestions?: string[]
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
        {suggestions.length > 0 && (
          <div className="btn-row">
            <span className="hint">Suggested:</span>
            {options
              .filter((d) => suggestions.includes(d.id))
              .map((d) => (
                <Button
                  key={d.id}
                  size="sm"
                  variant={defect === d.id ? 'primary' : 'default'}
                  onClick={() => setDefect(d.id)}
                >
                  {d.label}
                </Button>
              ))}
          </div>
        )}
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
