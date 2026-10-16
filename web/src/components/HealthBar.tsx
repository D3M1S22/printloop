import { USE_FIXTURES, WrongBackendError } from '../api'
import { useHealth } from '../api/hooks'
import { Badge } from './ui'

/** Stato dei servizi: chi fa la diagnosi (Gemma su AMD o operatore) e quale slicer verifica le patch. */
export function HealthBar() {
  const { data, error } = useHealth()
  if (error) {
    return (
      <div className="health" aria-label="Stato dei servizi" title={error.message}>
        <Badge tone="danger">
          {error instanceof WrongBackendError ? 'Backend sbagliato sulla porta API' : 'Backend non raggiungibile'}
        </Badge>
      </div>
    )
  }
  if (!data) return null
  const llm = data.llm?.mode === 'llm'
  const slicer = data.slicer?.available ?? false
  return (
    <div className="health" aria-label="Stato dei servizi">
      {USE_FIXTURES && <Badge tone="warn">Dati di esempio</Badge>}
      <Badge tone={llm ? 'ok' : 'warn'}>
        {llm ? `Diagnosi: ${data.llm.model ?? 'LLM'}` : 'Diagnosi: operatore (LLM offline)'}
      </Badge>
      <Badge tone={slicer ? 'ok' : 'danger'}>
        {slicer ? `Slicer: ${data.slicer.version ?? 'ok'}` : 'Slicer non trovato'}
      </Badge>
    </div>
  )
}
