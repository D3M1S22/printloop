import type { Attempt, Check, Preflight, Proposal, Validation } from '../api/types'
import { SOURCE_LABEL, checkLabel, delta, duration, num } from '../lib/format'
import { Badge, Notice } from './ui'

const STAGE_LABEL = { validation: 'the validator', slicing: 'slicing', preflight: 'the pre-flight' } as const
const ICON = { pass: '✓', fail: '✕', 'n/a': '–' } as const
const STATUS_TEXT = { pass: 'passed', fail: 'failed', 'n/a': 'not applicable' } as const

export function ChangeList({ proposal }: { proposal: Proposal }) {
  return (
    <div className="changes">
      {proposal.changes.map((c) => (
        <div key={c.key} className={c.companion ? 'change change--companion' : 'change'}>
          <span className="change__label">
            {c.label || c.key} <span className="muted mono">{c.key}</span>
          </span>
          <span className="change__values" aria-label={`from ${num(c.before, c.unit)} to ${num(c.after, c.unit)}`}>
            <del>{num(c.before, c.unit)}</del> → <ins>{num(c.after, c.unit)}</ins>
          </span>
          {c.reason && <span className="change__reason">{c.reason}</span>}
        </div>
      ))}
    </div>
  )
}

function CheckItem({ check }: { check: Check }) {
  const hasValues = check.before !== null || check.after !== null
  return (
    <li className="check" data-status={check.status}>
      <span className="check__icon" aria-hidden="true">
        {ICON[check.status]}
      </span>
      <span>
        <span className="check__title">{checkLabel(check)}</span> <span className="check__target">{check.target}</span>
        <span className="sr-only">: {STATUS_TEXT[check.status]}</span>
      </span>
      <span className="check__values">{hasValues ? `${num(check.before)} → ${num(check.after)}` : check.expected}</span>
      {check.detail && <span className="check__detail">{check.detail}</span>}
    </li>
  )
}

export function PreflightView({ preflight }: { preflight: Preflight }) {
  const side = preflight.side_effects
  const failed = [...preflight.checks, ...preflight.limits].filter((c) => c.status === 'fail').length
  return (
    <div className="stack">
      {preflight.ok ? (
        <Notice tone="ok" title="Pre-flight passed">
          The change is written in the G-code and has the expected effect on the toolpath; no limit exceeded.
        </Notice>
      ) : (
        <Notice tone="danger" title={`Pre-flight failed (${failed} ${failed === 1 ? 'check' : 'checks'})`}>
          Approving anyway requires a reason, which is kept in the audit log.
        </Notice>
      )}
      <div className="effects">
        <div className="effect">
          <span>Print time</span>
          <strong>{delta(side.print_time_s, 'time')}</strong>
          <small>{duration(side.print_time_s?.[1])}</small>
        </div>
        <div className="effect">
          <span>Filament</span>
          <strong>{delta(side.filament_g, 'grams')}</strong>
          <small>{num(side.filament_g?.[1] ?? null, 'g')}</small>
        </div>
        <div className="effect">
          <span>Layer</span>
          <strong>
            {side.layers?.[0] === side.layers?.[1] ? 'unchanged' : `${side.layers?.[0]} → ${side.layers?.[1]}`}
          </strong>
          <small>{side.layers?.[1] ?? '—'}</small>
        </div>
      </div>
      <div>
        <h3 className="section-title">G-code verification</h3>
        <ul className="checks">
          {preflight.checks.map((c, i) => (
            <CheckItem key={`c${i}`} check={c} />
          ))}
        </ul>
      </div>
      <div>
        <h3 className="section-title">Limits</h3>
        <ul className="checks">
          {preflight.limits.map((c, i) => (
            <CheckItem key={`l${i}`} check={c} />
          ))}
        </ul>
      </div>
    </div>
  )
}

function Attempts({ attempts }: { attempts: Attempt[] }) {
  if (attempts.length === 0) return null
  return (
    <details className="disclosure">
      <summary>Proposals discarded by the system before this one ({attempts.length})</summary>
      <div>
        {attempts.map((a, i) => (
          <p key={i}>
            <Badge plain>{SOURCE_LABEL[a.source]}</Badge>{' '}
            {a.changes.map((c) => `${c.key} → ${num(c.after)}`).join(', ')}: discarded by {STAGE_LABEL[a.stage]}.{' '}
            <span className="muted">{a.reason}</span>
          </p>
        ))}
      </div>
    </details>
  )
}

export function PatchReview({
  proposal,
  preflight,
  validation,
}: {
  proposal: Proposal
  preflight: Preflight | null
  validation: Validation | null
}) {
  return (
    <div className="stack">
      <div className="btn-row">
        <Badge tone="accent" plain>
          Proposed by: {SOURCE_LABEL[proposal.source]}
        </Badge>
        {proposal.model && <Badge plain>{proposal.model}</Badge>}
      </div>
      <ChangeList proposal={proposal} />
      {proposal.rationale && <p className="muted">{proposal.rationale}</p>}
      {proposal.expected_effect && (
        <p>
          <strong>Expected effect:</strong> {proposal.expected_effect}
        </p>
      )}
      {validation && validation.warnings.length > 0 && (
        <Notice tone="warn" title="Validator warnings">
          <ul className="evidence">
            {validation.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </Notice>
      )}
      <Attempts attempts={proposal.rejected_attempts} />
      {preflight && <PreflightView preflight={preflight} />}
    </div>
  )
}
