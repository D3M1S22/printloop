import type { RouteObject } from 'react-router'
import { NotFound, RouteError, Shell } from './components/Shell'
import { CasePage } from './pages/CasePage'
import { CasesPage } from './pages/CasesPage'

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Shell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <CasesPage /> },
      { path: 'cases/:id', element: <CasePage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]
