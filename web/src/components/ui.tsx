import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode, type Ref } from 'react'
import { ApiError } from '../api'
import type { CaseState } from '../api/types'
import { STATE_LABEL, STATE_TONE } from '../lib/format'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  ref?: Ref<HTMLButtonElement>
  variant?: 'primary' | 'danger' | 'ghost' | 'ok' | 'default'
  size?: 'sm' | 'md'
  busy?: boolean
}

export function Button({
  variant = 'default',
  size = 'md',
  busy = false,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  const classes = ['btn', variant !== 'default' && `btn--${variant}`, size === 'sm' && 'btn--sm', className]
    .filter(Boolean)
    .join(' ')
  return (
    <button type="button" className={classes} disabled={disabled || busy} aria-busy={busy || undefined} {...rest}>
      {busy && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  )
}

export function Card({
  title,
  subtitle,
  actions,
  accent,
  children,
}: {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  accent?: boolean
  children: ReactNode
}) {
  return (
    <section className={accent ? 'card card--accent' : 'card'}>
      {(title || actions) && (
        <header className="card__head">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className="card__body">{children}</div>
    </section>
  )
}

export type Tone = 'neutral' | 'info' | 'warn' | 'accent' | 'ok' | 'danger'

export function Badge({ tone = 'neutral', plain, children }: { tone?: Tone; plain?: boolean; children: ReactNode }) {
  const classes = ['badge', tone !== 'neutral' && `badge--${tone}`, plain && 'badge--plain'].filter(Boolean).join(' ')
  return <span className={classes}>{children}</span>
}

export function StateBadge({ state }: { state: CaseState }) {
  return <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge>
}

export function Notice({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'warn' | 'danger' | 'ok'
  title?: ReactNode
  children?: ReactNode
}) {
  return (
    <div className={`notice notice--${tone}`} role={tone === 'danger' ? 'alert' : undefined}>
      {title && <strong>{title}</strong>}
      {children}
    </div>
  )
}

export function ErrorNotice({ error, title = 'Operation failed' }: { error: unknown; title?: string }) {
  if (!error) return null
  const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
  return (
    <Notice tone="danger" title={title}>
      <span>{message}</span>
    </Notice>
  )
}

/**
 * Button that asks before acting: the first click turns it into question + confirm + cancel, inline.
 * Used for actions that discard data (delete, go back), where a modal would be heavier than the question.
 */
export function ConfirmButton({
  children,
  question,
  confirmLabel,
  onConfirm,
  busy = false,
  variant = 'ghost',
  size = 'md',
  title,
}: {
  children: ReactNode
  question: ReactNode
  confirmLabel: string
  onConfirm: () => void
  busy?: boolean
  variant?: ButtonProps['variant']
  size?: ButtonProps['size']
  title?: string
}) {
  const [asking, setAsking] = useState(false)
  const confirmRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (asking) confirmRef.current?.focus()
  }, [asking])

  if (!asking) {
    return (
      <Button variant={variant} size={size} title={title} onClick={() => setAsking(true)}>
        {children}
      </Button>
    )
  }
  return (
    <span className="confirm" role="group" aria-label="Confirmation">
      <span className="confirm__question">{question}</span>
      <Button ref={confirmRef} variant="danger" size={size} busy={busy} onClick={onConfirm}>
        {confirmLabel}
      </Button>
      <Button variant="ghost" size={size} disabled={busy} onClick={() => setAsking(false)}>
        Cancel
      </Button>
    </span>
  )
}

export function Spinner({ label }: { label: string }) {
  return (
    <p className="muted" role="status">
      <span
        className="spinner"
        aria-hidden="true"
        style={{ display: 'inline-block', verticalAlign: '-2px', marginRight: 8 }}
      />
      {label}
    </p>
  )
}

export function Severity({ level }: { level: number }) {
  return (
    <span className="severity" data-level={level} aria-hidden="true">
      <i />
      <i />
      <i />
    </span>
  )
}
