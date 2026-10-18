import { useId, useState } from 'react'
import type { DecisionRequest, EditOption } from '../api/types'
import { num } from '../lib/format'
import { Button, ErrorNotice } from './ui'

type Mode = 'idle' | 'edit' | 'stop'

/** Initial editor values: the proposed one if any, otherwise the project's current value. */
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
      setLocalError('A reason is required: it is kept in the case audit log.')
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
    if (keys.length === 0) return setLocalError('No value differs from the current one.')
    if (keys.length > 2) return setLocalError('At most 2 parameters per iteration.')
    const outOfRange = options.find((o) => o.key in e && (e[o.key]! < o.min || e[o.key]! > o.max))
    if (outOfRange)
      return setLocalError(
        `${outOfRange.label}: out of bounds ${num(outOfRange.min)}–${num(outOfRange.max, outOfRange.unit)}.`,
      )
    submit({ approved: false, reason: reason.trim() || 'values edited by the operator', edits: e }, false)
  }

  return (
    <div className="stack">
      <div className="field">
        <label htmlFor={reasonId}>Reason {preflightOk ? '(required to reject)' : '(required)'}</label>
        <textarea
          id={reasonId}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="E.g. I would rather try the fan first…"
        />
      </div>

      {mode === 'edit' && (
        <div className="edit-grid" role="group" aria-label="Edit the values">
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
                current {num(o.current, o.unit)} · bounds {num(o.min)}–{num(o.max, o.unit)} · suggested step{' '}
                {o.direction === 'up' ? '+' : '−'}
                {num(o.step, o.unit)}
              </span>
            </div>
          ))}
          <div className="btn-row">
            <Button variant="primary" busy={busy} onClick={recompute}>
              Re-slice and verify
            </Button>
            <Button variant="ghost" onClick={() => setMode('idle')}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {mode === 'stop' && (
        <div className="notice notice--warn">
          <strong>Stop the loop on this case?</strong>
          <span>The case is handed to the operator; the reason is kept in the audit log.</span>
          <div className="btn-row">
            <Button variant="danger" busy={busy} onClick={() => submit({ approved: false, reason, stop: true }, false)}>
              Yes, stop the loop
            </Button>
            <Button variant="ghost" onClick={() => setMode('idle')}>
              Cancel
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
            {preflightOk ? 'Approve and prepare the reprint' : 'Approve anyway'}
          </Button>
          <Button variant="danger" disabled={busy} onClick={reject}>
            Reject
          </Button>
          {options.length > 0 && (
            <Button disabled={busy} onClick={() => setMode('edit')}>
              Edit the values
            </Button>
          )}
          <Button variant="ghost" disabled={busy} onClick={() => setMode('stop')}>
            Stop the loop
          </Button>
        </div>
      )}
    </div>
  )
}
