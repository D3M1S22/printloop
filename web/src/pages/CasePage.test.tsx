import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import created from '../../fixtures/case_created.json'
import { fixtureApi } from '../api/fixtures'
import { createQueryClient } from '../queryClient'
import { routes } from '../routes'

// The page talks to the fixtures instead of the network.
vi.mock('../api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api')>()
  const { fixtureApi: api } = await import('../api/fixtures')
  return { ...original, api }
})

function renderCase(path = `/cases/${created.id}`) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { user: userEvent.setup(), router }
}

/** Moves the fixture case to the reprint step (first patch approved, waiting for the reprint). */
const approveFirstPatch = () => fixtureApi.decide(created.id, { approved: true, reason: '' })

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  fixtureApi.reset()
})
afterEach(() => vi.useRealTimers())

describe('CasePage: full loop on the fixtures', () => {
  it('photos → manual diagnosis → verified patch → approval → reprint', async () => {
    const { user } = renderCase()
    expect(await screen.findByRole('heading', { name: 'Bridge test' })).toBeInTheDocument()

    const photo = new File(['x'], 'front.jpg', { type: 'image/jpeg' })
    await user.upload(screen.getByLabelText(/Photos of the part: drop/), photo)
    await user.click(screen.getByRole('button', { name: 'Upload 1 photo' }))

    // LLM offline in the fixtures: operator diagnosis. "No defect" is not a defect to pick.
    const select = await screen.findByLabelText('Observed defect')
    expect(within(select).queryByRole('option', { name: 'No defect' })).not.toBeInTheDocument()
    await user.selectOptions(select, 'bridge_sagging')
    await user.click(screen.getByRole('radio', { name: /3 · severe/ }))
    await user.click(screen.getByRole('button', { name: 'Confirm the diagnosis' }))

    await user.click(await screen.findByRole('button', { name: 'Propose a verified patch' }))
    expect(await screen.findByText('Patch to approve', {}, { timeout: 5000 })).toBeInTheDocument()
    expect(screen.getByText('Pre-flight passed')).toBeInTheDocument()
    expect(screen.getByLabelText('from 100 mm/s to 80 mm/s')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Approve and prepare the reprint' }))
    expect(await screen.findByText('1. Print the approved patch')).toBeInTheDocument()
    const stepper = screen.getByRole('list', { name: 'Loop progress' })
    expect(
      within(stepper)
        .getByText(/Reprint/)
        .closest('li'),
    ).toHaveAttribute('aria-current', 'step')
  })

  it('closes the case with one click when the reprint is good', async () => {
    await approveFirstPatch()
    const { user } = renderCase()
    await user.click(await screen.findByRole('button', { name: '✓ Reprint OK, close the case' }))
    expect(await screen.findByText('Defect fixed')).toBeInTheDocument()
    expect(screen.getByText(/Reprint confirmed good by the operator/)).toBeInTheDocument()
  })

  it('goes back one step after saying what is discarded', async () => {
    await approveFirstPatch()
    const { user } = renderCase()
    await user.click(await screen.findByRole('button', { name: '↶ Step back' }))
    const panel = screen.getByRole('group', { name: 'Go back' })
    expect(panel).toHaveTextContent('Go back to the approval of iteration 1?')
    expect(panel).toHaveTextContent('This discards the approval of iteration 1')
    await user.click(within(panel).getByRole('button', { name: 'Go back' }))
    expect(await screen.findByText('Patch to approve')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Go back' })).not.toBeInTheDocument()
  })

  it('goes back from a completed step of the stepper', async () => {
    await approveFirstPatch()
    const { user } = renderCase()
    const stepper = await screen.findByRole('list', { name: 'Loop progress' })
    await user.click(within(stepper).getByRole('button', { name: /Diagnosis/ }))
    const panel = screen.getByRole('group', { name: 'Go back' })
    expect(panel).toHaveTextContent('Go back to the diagnosis of iteration 1?')
    await user.click(within(panel).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('group', { name: 'Go back' })).not.toBeInTheDocument()
  })

  it('deletes the case after a confirmation', async () => {
    const { user, router } = renderCase()
    await user.click(await screen.findByRole('button', { name: 'Delete case' }))
    expect(screen.getByText('Delete this case and all its files?')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(await screen.findByRole('heading', { name: 'Print cases' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
    await expect(fixtureApi.getCase(created.id)).rejects.toThrow('not found')
  })

  it('missing case', async () => {
    renderCase('/cases/nope')
    expect(await screen.findByText('Case not found', {}, { timeout: 3000 })).toBeInTheDocument()
  })
})
