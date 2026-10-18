import type { RouteObject } from 'react-router'
import { NotFound, RouteError, Shell } from './components/Shell'
import { CasePage } from './pages/CasePage'
import { CasesPage } from './pages/CasesPage'
import { LivePage } from './pages/LivePage'

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Shell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <CasesPage /> },
      { path: 'cases/:id', element: <CasePage /> },
      { path: 'live', element: <LivePage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]
