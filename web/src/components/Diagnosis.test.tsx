import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createQueryClient } from '../queryClient'
import { DetectorLine, ManualDiagnosisForm } from './Diagnosis'

vi.mock('../api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api')>()
  const { fixtureApi: api } = await import('../api/fixtures')
  return { ...original, api }
})

const wrap = (ui: React.ReactNode) =>
  render(<QueryClientProvider client={createQueryClient()}>{ui}</QueryClientProvider>)

describe('two-model diagnosis UI', () => {
  it('shows what the detector saw and whether the diagnosis agrees', async () => {
    wrap(
      <DetectorLine
        detector={{ defects: ['stringing', 'blobs'], primary: 'stringing', agreement: 'disagree', photos: 2 }}
      />,
    )
    expect(await screen.findByText('Stringing, Blobs / zits')).toBeInTheDocument()
    expect(screen.getByText('disagrees')).toBeInTheDocument()
  })

  it('offers the suggested defects as one-click picks', async () => {
    const onSubmit = vi.fn()
    wrap(<ManualDiagnosisForm onSubmit={onSubmit} busy={false} suggestions={['stringing', 'under_extrusion']} />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Under-extrusion' }))
    expect(screen.getByLabelText('Observed defect')).toHaveValue('under_extrusion')
    await user.click(screen.getByRole('button', { name: 'Confirm the diagnosis' }))
    expect(onSubmit).toHaveBeenCalledWith('under_extrusion', 2, '')
  })
})
