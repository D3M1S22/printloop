import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import created from '../../fixtures/case_created.json'
import { fixtureApi } from '../api/fixtures'
import { createQueryClient } from '../queryClient'
import { routes } from '../routes'

// La pagina parla con le fixture invece che con la rete.
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
  return userEvent.setup()
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  fixtureApi.reset()
})
afterEach(() => vi.useRealTimers())

describe('CasePage: loop completo sulle fixture', () => {
  it('foto → diagnosi manuale → patch verificata → approvazione → ristampa', async () => {
    const user = renderCase()
    expect(await screen.findByRole('heading', { name: 'Bridge test' })).toBeInTheDocument()

    const photo = new File(['x'], 'front.jpg', { type: 'image/jpeg' })
    await user.upload(screen.getByLabelText(/Foto del pezzo: trascina/), photo)
    await user.click(screen.getByRole('button', { name: 'Carica 1 foto' }))

    // LLM offline nelle fixture: diagnosi dell'operatore
    await user.selectOptions(await screen.findByLabelText('Difetto osservato'), 'bridge_sagging')
    await user.click(screen.getByRole('radio', { name: /3 · grave/ }))
    await user.click(screen.getByRole('button', { name: 'Conferma la diagnosi' }))

    await user.click(await screen.findByRole('button', { name: 'Proponi una patch verificata' }))
    expect(await screen.findByText('Patch da approvare', {}, { timeout: 5000 })).toBeInTheDocument()
    expect(screen.getByText('Pre-flight superato')).toBeInTheDocument()
    const change = screen.getByLabelText('da 100 mm/s a 80 mm/s')
    expect(change).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Approva e prepara la ristampa' }))
    expect(await screen.findByText('1. Stampa la patch approvata')).toBeInTheDocument()
    const stepper = screen.getByRole('list', { name: 'Avanzamento del loop' })
    expect(
      within(stepper)
        .getByText(/Ristampa/)
        .closest('li'),
    ).toHaveAttribute('aria-current', 'step')
  })

  it('caso inesistente', async () => {
    renderCase('/cases/nope')
    expect(await screen.findByText('Caso non trovato', {}, { timeout: 3000 })).toBeInTheDocument()
  })
})
