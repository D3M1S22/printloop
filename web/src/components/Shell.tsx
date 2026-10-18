import { Link, Outlet, useRouteError } from 'react-router'
import { HealthBar } from './HealthBar'
import { ErrorNotice } from './ui'

export function Shell() {
  return (
    <>
      <a className="sr-only" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar__inner">
          <Link to="/" className="brand">
            <img src="/favicon.svg" alt="" />
            PrintLoop <small>defect → verified patch</small>
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
        ← Back to the cases
      </Link>
      <ErrorNotice error={error instanceof Error ? error : 'Page not found'} title="Something went wrong" />
    </main>
  )
}

export function NotFound() {
  return (
    <main className="page stack">
      <h1>Page not found</h1>
      <Link to="/">Back to the cases</Link>
    </main>
  )
}
