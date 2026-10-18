import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { EditOption } from '../api/types'
import { DecisionPanel } from './DecisionPanel'

const options: EditOption[] = [
  {
    key: 'bridge_speed',
    label: 'Bridge speed',
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
    label: 'Bridge flow',
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
  it('approves without a reason when the pre-flight passed', async () => {
    const { onDecide, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Approve and prepare the reprint' }))
    expect(onDecide).toHaveBeenCalledWith({ approved: true, reason: '' })
  })

  it('asks for a reason to reject', async () => {
    const { onDecide, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Reject' }))
    expect(onDecide).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('A reason is required')
    await user.type(screen.getByLabelText(/Reason/), 'fan first')
    await user.click(screen.getByRole('button', { name: 'Reject' }))
    expect(onDecide).toHaveBeenCalledWith({ approved: false, reason: 'fan first' })
  })

  it('with a failed pre-flight approving needs a reason too', async () => {
    const { onDecide, user } = setup(false)
    await user.click(screen.getByRole('button', { name: 'Approve anyway' }))
    expect(onDecide).not.toHaveBeenCalled()
  })

  it('sends only the values that differ from the current ones', async () => {
    const { onDecide, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Edit the values' }))
    const flow = screen.getByLabelText('Bridge flow')
    await user.clear(flow)
    await user.type(flow, '0.9')
    await user.click(screen.getByRole('button', { name: 'Re-slice and verify' }))
    expect(onDecide).toHaveBeenCalledWith({
      approved: false,
      reason: 'values edited by the operator',
      edits: { bridge_speed: 80, bridge_flow: 0.9 },
    })
  })

  it('blocks values out of bounds', async () => {
    const { onDecide, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Edit the values' }))
    const speed = screen.getByLabelText('Bridge speed')
    await user.clear(speed)
    await user.type(speed, '5')
    await user.click(screen.getByRole('button', { name: 'Re-slice and verify' }))
    expect(onDecide).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('out of bounds')
  })
})
