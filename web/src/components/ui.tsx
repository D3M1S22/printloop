import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { ApiError } from '../api'
import type { CaseState } from '../api/types'
import { STATE_LABEL, STATE_TONE } from '../lib/format'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'danger' | 'ghost' | 'default'
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

export function ErrorNotice({ error, title = 'Operazione non riuscita' }: { error: unknown; title?: string }) {
  if (!error) return null
  const message = error instanceof ApiError || error instanceof Error ? error.message : String(error)
  return (
    <Notice tone="danger" title={title}>
      <span>{message}</span>
    </Notice>
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
