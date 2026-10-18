import { useId, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import {
  useCases,
  useConfirmSuccess,
  useLive,
  useLiveAttach,
  useLiveDismiss,
  useLiveStart,
  useDefectLabel,
  useLiveStop,
} from '../api/hooks'
import type { LiveAlert, LiveSession, LiveSourceKind, LiveState } from '../api/types'
import { Badge, Button, Card, ErrorNotice, Notice, Spinner } from '../components/ui'
import { dateTime } from '../lib/format'

const SOURCE_LABEL: Record<LiveSourceKind, string> = {
  replay: 'Replay a folder of frames',
  p1s: 'P1S camera (LAN)',
  url: 'Snapshot URL (phone, webcam)',
}

const STATUS_LABEL: Record<LiveSession['status'], string> = {
  running: 'Monitoring',
  stopped: 'Stopped',
  finished: 'Finished',
  error: 'Error',
}

/** A frame served by the API; in fixture mode the file does not exist and a placeholder is shown. */
function Frame({ url, alt, small }: { url?: string; alt: string; small?: boolean }) {
  const [failed, setFailed] = useState(false)
  if (!url || failed)
    return <div className={small ? 'live-thumb photo__placeholder' : 'photo__placeholder live-frame'}>{alt}</div>
  return <img className={small ? 'live-thumb' : 'live-frame'} src={url} alt={alt} onError={() => setFailed(true)} />
}

function StartForm({ state }: { state: LiveState }) {
  const start = useLiveStart()
  const { data: cases } = useCases()
  const ids = { source: useId(), dir: useId(), url: useId(), interval: useId(), case: useId() }
  const [source, setSource] = useState<LiveSourceKind>(state.defaults.source)
  const [dir, setDir] = useState(state.defaults.replay_dir ?? '')
  const [url, setUrl] = useState(state.defaults.snapshot_url ?? '')
  const [interval, setInterval] = useState(String(state.defaults.interval_s))
  const [caseId, setCaseId] = useState('')
  const reprints = cases?.filter((c) => c.state === 'awaiting_photos' && c.iteration > 1) ?? []
  const detectorOn = state.detector.mode === 'on'

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault()
        start.mutate({
          source,
          replay_dir: source === 'replay' ? dir : undefined,
          url: source === 'url' ? url : undefined,
          interval_s: Number(interval) || undefined,
          case_id: caseId || undefined,
        })
      }}
    >
      {!detectorOn && (
        <Notice tone="warn" title="Detector not configured">
          Set VISION_LLM_BASE_URL to the fine-tuned Gemma 4 E4B server (infra/serve_vision_e4b.sh) and restart the API.
        </Notice>
      )}
      <div className="field">
        <label htmlFor={ids.source}>Frame source</label>
        <select id={ids.source} value={source} onChange={(e) => setSource(e.target.value as LiveSourceKind)}>
          {(Object.keys(SOURCE_LABEL) as LiveSourceKind[]).map((k) => (
            <option key={k} value={k} disabled={k === 'p1s' && !state.printer.configured}>
              {SOURCE_LABEL[k]}
              {k === 'p1s' && !state.printer.configured ? ' (set PRINTER_IP and PRINTER_ACCESS_CODE)' : ''}
            </option>
          ))}
        </select>
      </div>
      {source === 'replay' && (
        <div className="field">
          <label htmlFor={ids.dir}>Folder of frames on the server</label>
          <input id={ids.dir} type="text" value={dir} onChange={(e) => setDir(e.target.value)} required />
          <span className="hint">Images played in file-name order, one per tick (a recorded print).</span>
        </div>
      )}
      {source === 'url' && (
        <div className="field">
          <label htmlFor={ids.url}>Snapshot URL</label>
          <input id={ids.url} type="url" value={url} onChange={(e) => setUrl(e.target.value)} required />
        </div>
      )}
      <div className="field">
        <label htmlFor={ids.interval}>Seconds between frames</label>
        <input
          id={ids.interval}
          type="number"
          min={1}
          max={600}
          value={interval}
          onChange={(e) => setInterval(e.target.value)}
        />
        <span className="hint">The detector answers in under a second; 10 s is plenty for a print.</span>
      </div>
      <div className="field">
        <label htmlFor={ids.case}>Reprint of a case (optional)</label>
        <select id={ids.case} value={caseId} onChange={(e) => setCaseId(e.target.value)}>
          <option value="">Not linked</option>
          {reprints.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} · iteration {c.iteration}
            </option>
          ))}
        </select>
        <span className="hint">The evidence frames can then become the photos of the reprint.</span>
      </div>
      <ErrorNotice error={start.error} title="Monitoring not started" />
      <div className="btn-row">
        <Button type="submit" variant="primary" busy={start.isPending} disabled={!detectorOn}>
          Start monitoring
        </Button>
      </div>
    </form>
  )
}

function AlertItem({ alert, session }: { alert: LiveAlert; session: LiveSession }) {
  const label = useDefectLabel()
  const dismiss = useLiveDismiss()
  const pause = alert.level === 'pause_proposed'
  const active = !alert.cleared_at && !alert.dismissed
  return (
    <li className="live-alert" data-level={alert.level} data-active={active}>
      <div className="btn-row">
        <Badge tone={pause ? 'danger' : 'warn'}>{pause ? 'Pause proposed' : 'Warning'}</Badge>
        <strong>{label(alert.defect)}</strong>
        <span className="muted">
          since {dateTime(alert.since)}
          {alert.cleared_at ? ` · cleared ${dateTime(alert.cleared_at)}` : ''}
          {alert.dismissed ? ` · dismissed${alert.dismiss_reason ? `: ${alert.dismiss_reason}` : ''}` : ''}
        </span>
      </div>
      <div className="live-thumbs">
        {alert.frames.map((f, i) => (
          <Frame key={`${f}-${i}`} url={alert.frame_urls[i]} alt={`evidence ${i + 1}`} small />
        ))}
      </div>
      {active && pause && session.status === 'running' && (
        <p className="muted">
          Check the print and pause it on the printer if needed. PrintLoop never stops a print on its own.
        </p>
      )}
      {active && (
        <div className="btn-row">
          <Button
            size="sm"
            variant="ghost"
            busy={dismiss.isPending}
            onClick={() => dismiss.mutate({ id: alert.id, reason: '' })}
          >
            Dismiss
          </Button>
        </div>
      )}
    </li>
  )
}

/** After the print: evidence frames → photos of a case, or "Reprint OK" when nothing was raised. */
function AfterPrint({ session }: { session: LiveSession }) {
  const navigate = useNavigate()
  const { data: cases } = useCases()
  const attach = useLiveAttach()
  const confirm = useConfirmSuccess()
  const selectId = useId()
  const [caseId, setCaseId] = useState(session.case_id ?? '')
  const open = cases?.filter((c) => ['awaiting_photos', 'ready', 'needs_info'].includes(c.state)) ?? []
  const linked = cases?.find((c) => c.id === session.case_id)
  const alerts = session.alerts.filter((a) => !a.dismissed)

  if (alerts.length === 0) {
    return (
      <Card title="No alert during this print">
        {linked?.allowed_actions.includes('confirm_success') ? (
          <>
            <p className="muted">If the reprint of “{linked.name}” looks good, close the case.</p>
            <div className="btn-row">
              <Button variant="ok" busy={confirm.isPending} onClick={() => confirm.mutate({ id: linked.id })}>
                ✓ Reprint OK
              </Button>
            </div>
            <ErrorNotice error={confirm.error} />
            {confirm.isSuccess && <Notice tone="ok">Case closed as fixed.</Notice>}
          </>
        ) : (
          <p className="muted">
            Nothing to report. Check the part anyway: the detector has not been tuned on this camera yet.
          </p>
        )}
      </Card>
    )
  }
  return (
    <Card
      title="Use the evidence"
      subtitle="Up to 4 evidence frames become the photos of the case's current iteration."
    >
      <div className="field">
        <label htmlFor={selectId}>Case</label>
        <select id={selectId} value={caseId} onChange={(e) => setCaseId(e.target.value)}>
          <option value="">Choose…</option>
          {open.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} · iteration {c.iteration}
            </option>
          ))}
        </select>
        <span className="hint">
          No case for this print yet? <Link to="/">Create it from its 3MF</Link>, then come back here.
        </span>
      </div>
      <ErrorNotice error={attach.error} title="Evidence not attached" />
      <div className="btn-row">
        <Button
          variant="primary"
          disabled={!caseId}
          busy={attach.isPending}
          onClick={() =>
            attach.mutate({ caseId, sessionId: session.id }, { onSuccess: (c) => void navigate(`/cases/${c.id}`) })
          }
        >
          Attach evidence as photos
        </Button>
      </div>
    </Card>
  )
}

function SessionView({ session }: { session: LiveSession }) {
  const label = useDefectLabel()
  const stop = useLiveStop()
  const last = session.last
  const running = session.status === 'running'
  const positives = Object.entries(session.counts.positives)
  return (
    <>
      <Card
        title="Latest frame"
        subtitle={last ? `${last.name || last.frame_id} · ${dateTime(last.taken_at)}` : undefined}
        actions={
          running ? (
            <Button variant="danger" size="sm" busy={stop.isPending} onClick={() => stop.mutate()}>
              Stop
            </Button>
          ) : undefined
        }
      >
        {last ? (
          <>
            <Frame url={last.frame_url} alt={`frame ${last.name || last.frame_id}`} />
            <div className="btn-row" aria-live="polite">
              {last.error ? (
                <Badge tone="warn">detector error</Badge>
              ) : last.defects.length ? (
                last.defects.map((d) => (
                  <Badge key={d} tone="warn">
                    {label(d)}
                  </Badge>
                ))
              ) : (
                <Badge tone="ok">No defect</Badge>
              )}
              {last.latency_ms !== null && <span className="muted">{Math.round(last.latency_ms)} ms</span>}
            </div>
          </>
        ) : (
          <Spinner label="Waiting for the first frame…" />
        )}
        <ErrorNotice error={stop.error} />
      </Card>
      <Card
        title={`Alerts (${session.alerts.length})`}
        subtitle="A defect must persist over several frames to raise an alert."
      >
        {session.alerts.length === 0 ? (
          <p className="muted">No alert so far.</p>
        ) : (
          <ul className="live-alerts">
            {[...session.alerts].reverse().map((a) => (
              <AlertItem key={a.id} alert={a} session={session} />
            ))}
          </ul>
        )}
      </Card>
      {!running && <AfterPrint session={session} />}
      {positives.length > 0 && (
        <Card title="Detections so far">
          <div className="btn-row">
            {positives.map(([d, n]) => (
              <Badge key={d} plain>
                {label(d)}: {n} {n === 1 ? 'frame' : 'frames'}
              </Badge>
            ))}
          </div>
        </Card>
      )}
    </>
  )
}

function SessionSummary({ session }: { session: LiveSession }) {
  const t = session.thresholds
  return (
    <Card title="Session">
      <dl className="kv">
        <dt>Status</dt>
        <dd>{STATUS_LABEL[session.status]}</dd>
        <dt>Source</dt>
        <dd>{session.source.detail ?? session.source.kind}</dd>
        <dt>Every</dt>
        <dd>{session.interval_s} s</dd>
        <dt>Frames analysed</dt>
        <dd>
          {session.counts.frames}
          {session.counts.errors ? ` · ${session.counts.errors} errors` : ''}
        </dd>
        <dt>Detector</dt>
        <dd>
          {session.detector.model ?? '—'}
          {session.detector.latency_p50_ms ? ` · ${Math.round(session.detector.latency_p50_ms)} ms` : ''}
        </dd>
        <dt>Thresholds</dt>
        <dd>
          pause {t.pause_k}/{t.pause_n} · warning {t.alert_k}/{t.alert_n}
        </dd>
        {session.case_id && (
          <>
            <dt>Reprint of</dt>
            <dd>
              <Link to={`/cases/${session.case_id}`}>case {session.case_id}</Link>
            </dd>
          </>
        )}
      </dl>
    </Card>
  )
}

export function LivePage() {
  const { data, isLoading, error } = useLive()
  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>Live monitoring</h1>
          <p className="page-head__meta">
            The fine-tuned Gemma 4 E4B checks one camera frame at a time; only defects that persist raise an alert.
          </p>
        </div>
      </div>
      {isLoading && <Spinner label="Loading…" />}
      <ErrorNotice error={error} title="Live monitoring unavailable" />
      {data && (
        <div className="layout">
          <div className="stack">
            {data.session ? (
              <SessionView session={data.session} />
            ) : (
              <Card title="No session yet">
                <p className="muted">Start monitoring a print from the panel on the right.</p>
              </Card>
            )}
          </div>
          <aside className="stack" aria-label="Session settings">
            {data.session && <SessionSummary session={data.session} />}
            {!data.running && (
              <Card title={data.session ? 'New session' : 'Start monitoring'}>
                <StartForm state={data} />
              </Card>
            )}
          </aside>
        </div>
      )}
    </main>
  )
}
