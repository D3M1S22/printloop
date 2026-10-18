import { QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { fixtureApi } from '../api/fixtures'
import { createQueryClient } from '../queryClient'
import { routes } from '../routes'

vi.mock('../api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api')>()
  const { fixtureApi: api } = await import('../api/fixtures')
  return { ...original, api }
})

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  fixtureApi.reset()
})
afterEach(() => vi.useRealTimers())

describe('LivePage', () => {
  it('starts a replay session and shows a pause proposal once a defect persists', async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/live'] })} />
      </QueryClientProvider>,
    )
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    expect(await screen.findByRole('heading', { name: 'Live monitoring' })).toBeInTheDocument()
    expect(await screen.findByLabelText('Folder of frames on the server')).toHaveValue('data/live/demo')
    await user.click(screen.getByRole('button', { name: 'Start monitoring' }))
    expect(await screen.findByRole('button', { name: 'Stop' })).toBeInTheDocument()
    expect(screen.getByText('No alert so far.')).toBeInTheDocument()
    for (let i = 0; i < 8 && !screen.queryByText('Pause proposed'); i++) {
      await act(() => vi.advanceTimersByTimeAsync(2100))
    }
    expect(screen.getByText('Pause proposed')).toBeInTheDocument()
    expect(screen.getByText(/PrintLoop never stops a print on its own/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Stop' }))
    expect(await screen.findByText('Use the evidence')).toBeInTheDocument()
  })
})
