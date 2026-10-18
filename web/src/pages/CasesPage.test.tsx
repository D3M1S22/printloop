import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import created from '../../fixtures/case_created.json'
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

const rowOf = async (name: string) => (await screen.findByRole('link', { name })).closest('tr')!

beforeEach(() => fixtureApi.reset())

describe('CasesPage', () => {
  it('opens the case when clicking anywhere on the row', async () => {
    const user = renderList()
    const row = await rowOf('Bridge test')
    await user.click(within(row).getByText('Awaiting photos'))
    expect(await screen.findByRole('heading', { name: 'Bridge test' })).toBeInTheDocument()
  })

  it('shows the next step for each case', async () => {
    renderList()
    expect(await screen.findByText('Upload photos →')).toBeInTheDocument()
    expect(screen.getByText('Open →')).toBeInTheDocument() // escalated case
  })

  it('confirms a good reprint from the list', async () => {
    await fixtureApi.decide(created.id, { approved: true, reason: '' })
    const user = renderList()
    const row = await rowOf('Bridge test')
    expect(within(await rowOf('Motor bracket')).queryByRole('button', { name: '✓ Reprint OK' })).toBeNull()
    await user.click(within(row).getByRole('button', { name: '✓ Reprint OK' }))
    expect(await within(row).findByText(/Defect fixed/)).toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: '✓ Reprint OK' })).toBeNull()
  })

  it('deletes a case after a confirmation, without opening it', async () => {
    const user = renderList()
    const row = await rowOf('Motor bracket')
    await user.click(within(row).getByRole('button', { name: 'Delete' }))
    expect(within(row).getByText('Delete “Motor bracket” and all its files?')).toBeInTheDocument()
    await user.click(within(row).getByRole('button', { name: 'Delete' }))
    expect(await screen.findByRole('link', { name: 'Bridge test' })).toBeInTheDocument()
    await vi.waitFor(() => expect(screen.queryByRole('link', { name: 'Motor bracket' })).toBeNull())
    expect(screen.getByRole('heading', { name: 'Print cases' })).toBeInTheDocument()
  })
})
