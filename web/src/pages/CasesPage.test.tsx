import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
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

function renderList() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/'] })} />
    </QueryClientProvider>,
  )
  return userEvent.setup()
}

beforeEach(() => fixtureApi.reset())

describe('CasesPage', () => {
  it('apre il caso cliccando un punto qualsiasi della riga', async () => {
    const user = renderList()
    const name = await screen.findByRole('link', { name: 'Bridge test' })
    const row = name.closest('tr')!
    await user.click(within(row).getByText('In attesa di foto'))
    expect(await screen.findByRole('heading', { name: 'Bridge test' })).toBeInTheDocument()
  })

  it('mostra il prossimo passo per ogni caso', async () => {
    renderList()
    expect(await screen.findByText('Carica le foto →')).toBeInTheDocument()
    expect(screen.getByText('Apri →')).toBeInTheDocument() // caso in escalation
  })
})
