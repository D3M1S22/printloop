import { USE_FIXTURES, WrongBackendError } from '../api'
import { useHealth } from '../api/hooks'
import { Badge } from './ui'

/** Service status: who diagnoses (Gemma on AMD or the operator) and which slicer verifies the patches. */
export function HealthBar() {
  const { data, error } = useHealth()
  if (error) {
    return (
      <div className="health" aria-label="Service status" title={error.message}>
        <Badge tone="danger">
          {error instanceof WrongBackendError ? 'Wrong backend on the API port' : 'Backend unreachable'}
        </Badge>
      </div>
    )
  }
  if (!data) return null
  const llm = data.llm?.mode === 'llm'
  const slicer = data.slicer?.available ?? false
  return (
    <div className="health" aria-label="Service status">
      {USE_FIXTURES && <Badge tone="warn">Sample data</Badge>}
      <Badge tone={llm ? 'ok' : 'warn'}>
        {llm ? `Diagnosis: ${data.llm.model ?? 'LLM'}` : 'Diagnosis: operator (LLM offline)'}
      </Badge>
      <Badge tone={slicer ? 'ok' : 'danger'}>
        {slicer ? `Slicer: ${data.slicer.version ?? 'ok'}` : 'Slicer not found'}
      </Badge>
    </div>
  )
}
