import React from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { ToastProvider } from './context/ToastContext'
import { UserProvider } from './context/UserContext'
import DagPage from './pages/dag/DagPage'
import IntegrationDetailPage from './pages/detail/IntegrationDetailPage'
import IntegrationsPage from './pages/list/IntegrationsPage'
import NotFoundPage from './pages/NotFoundPage'
import './styles/global.css'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <IntegrationsPage /> },
      { path: 'integrations/:id', element: <IntegrationDetailPage /> },
      { path: 'integrations/:id/dag', element: <DagPage /> },
      { path: 'dag', element: <DagPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <UserProvider>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </UserProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
