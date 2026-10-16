import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { EditOption } from '../api/types'
import { DecisionPanel } from './DecisionPanel'

const options: EditOption[] = [
  {
    key: 'bridge_speed',
    label: 'Velocità dei bridge',
    unit: 'mm/s',
    step: 20,
    direction: 'down',
    min: 10,
    max: 100,
    current: 100,
    proposed: 80,
  },
  {
    key: 'bridge_flow',
    label: 'Flusso dei bridge',
    unit: 'x',
    step: 0.05,
    direction: 'down',
    min: 0.7,
    max: 1.2,
    current: 1,
    proposed: null,
  },
]

function setup(preflightOk = true) {
  const onDecide = vi.fn()
  render(<DecisionPanel options={options} preflightOk={preflightOk} onDecide={onDecide} busy={false} error={null} />)
  return { onDecide, user: userEvent.setup() }
}

describe('DecisionPanel', () => {
  it('approva senza motivazione se il pre-flight è superato', async () => {
    const { onDecide, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Approva e prepara la ristampa' }))
    expect(onDecide).toHaveBeenCalledWith({ approved: true, reason: '' })
  })

  it('chiede la motivazione per rifiutare', async () => {
    const { onDecide, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Rifiuta' }))
    expect(onDecide).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('Serve una motivazione')
    await user.type(screen.getByLabelText(/Motivazione/), 'prima la ventola')
    await user.click(screen.getByRole('button', { name: 'Rifiuta' }))
    expect(onDecide).toHaveBeenCalledWith({ approved: false, reason: 'prima la ventola' })
  })

  it('con pre-flight fallito serve la motivazione anche per approvare', async () => {
    const { onDecide, user } = setup(false)
    await user.click(screen.getByRole('button', { name: 'Approva comunque' }))
    expect(onDecide).not.toHaveBeenCalled()
  })

  it('invia solo i valori diversi da quelli attuali', async () => {
    const { onDecide, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Modifica i valori' }))
    const flow = screen.getByLabelText('Flusso dei bridge')
    await user.clear(flow)
    await user.type(flow, '0.9')
    await user.click(screen.getByRole('button', { name: 'Ricalcola slicing e verifica' }))
    expect(onDecide).toHaveBeenCalledWith({
      approved: false,
      reason: 'valori modificati dall’operatore',
      edits: { bridge_speed: 80, bridge_flow: 0.9 },
    })
  })

  it('blocca i valori fuori dai limiti', async () => {
    const { onDecide, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Modifica i valori' }))
    const speed = screen.getByLabelText('Velocità dei bridge')
    await user.clear(speed)
    await user.type(speed, '5')
    await user.click(screen.getByRole('button', { name: 'Ricalcola slicing e verifica' }))
    expect(onDecide).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('fuori dai limiti')
  })
})
