import { useId, useState } from 'react'
import type { DecisionRequest, EditOption } from '../api/types'
import { num } from '../lib/format'
import { Button, ErrorNotice } from './ui'

type Mode = 'idle' | 'edit' | 'stop'

/** Valori iniziali dell'editor: quello proposto se c'è, altrimenti il valore attuale del progetto. */
const initialValues = (options: EditOption[]) =>
  Object.fromEntries(options.map((o) => [o.key, String(o.proposed ?? o.current)]))

export function DecisionPanel({
  options,
  preflightOk,
  onDecide,
  busy,
  error,
}: {
  options: EditOption[]
  preflightOk: boolean
  onDecide: (req: DecisionRequest) => void
  busy: boolean
  error: unknown
}) {
  const reasonId = useId()
  const [mode, setMode] = useState<Mode>('idle')
  const [reason, setReason] = useState('')
  const [values, setValues] = useState<Record<string, string>>(() => initialValues(options))
  const [localError, setLocalError] = useState<string | null>(null)

  const edits = () => {
    const out: Record<string, number> = {}
    for (const o of options) {
      const raw = values[o.key]
      const value = raw === undefined || raw === '' ? NaN : Number(raw)
      if (Number.isNaN(value)) continue
      if (Math.abs(value - o.current) > 1e-9) out[o.key] = value
    }
    return out
  }

  const submit = (req: DecisionRequest, needsReason: boolean) => {
    if (needsReason && !reason.trim()) {
      setLocalError('Serve una motivazione: resta nell’audit del caso.')
      return
    }
    setLocalError(null)
    onDecide({ ...req, reason: req.reason.trim() })
  }

  const approve = () => submit({ approved: true, reason }, !preflightOk)
  const reject = () => submit({ approved: false, reason }, true)
  const recompute = () => {
    const e = edits()
    const keys = Object.keys(e)
    if (keys.length === 0) return setLocalError('Nessun valore diverso da quello attuale.')
    if (keys.length > 2) return setLocalError('Al massimo 2 parametri per iterazione.')
    const outOfRange = options.find((o) => o.key in e && (e[o.key]! < o.min || e[o.key]! > o.max))
    if (outOfRange)
      return setLocalError(
        `${outOfRange.label}: fuori dai limiti ${num(outOfRange.min)}–${num(outOfRange.max, outOfRange.unit)}.`,
      )
    submit({ approved: false, reason: reason.trim() || 'valori modificati dall’operatore', edits: e }, false)
  }

  return (
    <div className="stack">
      <div className="field">
        <label htmlFor={reasonId}>Motivazione {preflightOk ? '(obbligatoria per rifiutare)' : '(obbligatoria)'}</label>
        <textarea
          id={reasonId}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Es. preferisco provare prima con la ventola…"
        />
      </div>

      {mode === 'edit' && (
        <div className="edit-grid" role="group" aria-label="Modifica dei valori">
          {options.map((o) => (
            <div className="edit-row" key={o.key}>
              <label htmlFor={`edit-${o.key}`}>{o.label}</label>
              <input
                id={`edit-${o.key}`}
                type="number"
                inputMode="decimal"
                min={o.min}
                max={o.max}
                step={o.step < 1 ? 0.01 : 1}
                value={values[o.key] ?? ''}
                onChange={(e) => setValues((v) => ({ ...v, [o.key]: e.target.value }))}
              />
              <span className="hint">
                attuale {num(o.current, o.unit)} · limiti {num(o.min)}–{num(o.max, o.unit)} · passo consigliato{' '}
                {o.direction === 'up' ? '+' : '−'}
                {num(o.step, o.unit)}
              </span>
            </div>
          ))}
          <div className="btn-row">
            <Button variant="primary" busy={busy} onClick={recompute}>
              Ricalcola slicing e verifica
            </Button>
            <Button variant="ghost" onClick={() => setMode('idle')}>
              Annulla
            </Button>
          </div>
        </div>
      )}

      {mode === 'stop' && (
        <div className="notice notice--warn">
          <strong>Chiudere il loop su questo caso?</strong>
          <span>Il caso passa all'operatore; la motivazione resta nell'audit.</span>
          <div className="btn-row">
            <Button variant="danger" busy={busy} onClick={() => submit({ approved: false, reason, stop: true }, false)}>
              Sì, ferma il loop
            </Button>
            <Button variant="ghost" onClick={() => setMode('idle')}>
              Annulla
            </Button>
          </div>
        </div>
      )}

      {localError && (
        <p className="notice notice--warn" role="alert">
          {localError}
        </p>
      )}
      <ErrorNotice error={error} />

      {mode === 'idle' && (
        <div className="btn-row">
          <Button variant="primary" busy={busy} onClick={approve}>
            {preflightOk ? 'Approva e prepara la ristampa' : 'Approva comunque'}
          </Button>
          <Button variant="danger" disabled={busy} onClick={reject}>
            Rifiuta
          </Button>
          {options.length > 0 && (
            <Button disabled={busy} onClick={() => setMode('edit')}>
              Modifica i valori
            </Button>
          )}
          <Button variant="ghost" disabled={busy} onClick={() => setMode('stop')}>
            Ferma il loop
          </Button>
        </div>
      )}
    </div>
  )
}
