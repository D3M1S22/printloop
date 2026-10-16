import { Link, Outlet, useRouteError } from 'react-router'
import { HealthBar } from './HealthBar'
import { ErrorNotice } from './ui'

export function Shell() {
  return (
    <>
      <a className="sr-only" href="#main">
        Vai al contenuto
      </a>
      <header className="topbar">
        <div className="topbar__inner">
          <Link to="/" className="brand">
            <img src="/favicon.svg" alt="" />
            PrintLoop <small>difetto → patch verificata</small>
          </Link>
          <span className="topbar__spacer" />
          <HealthBar />
        </div>
      </header>
      <div id="main">
        <Outlet />
      </div>
    </>
  )
}

export function RouteError() {
  const error = useRouteError()
  return (
    <main className="page stack">
      <Link className="back" to="/">
        ← Torna ai casi
      </Link>
      <ErrorNotice error={error instanceof Error ? error : 'Pagina non trovata'} title="Qualcosa è andato storto" />
    </main>
  )
}

export function NotFound() {
  return (
    <main className="page stack">
      <h1>Pagina non trovata</h1>
      <Link to="/">Torna ai casi</Link>
    </main>
  )
}
