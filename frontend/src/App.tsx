import { useEffect, useRef } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import Header from './components/Header'
import { useUser } from './context/UserContext'

export default function App() {
  const location = useLocation()
  const mainRef = useRef<HTMLElement>(null)
  const firstRender = useRef(true)
  const { loading, error } = useUser()

  useEffect(() => {
    // Move focus to the page content on client-side navigation.
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    mainRef.current?.focus()
  }, [location.pathname])

  return (
    <>
      <Header />
      <main id="main" className="app-main" ref={mainRef} tabIndex={-1}>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : error ? (
          <div className="error-note" role="alert">
            Could not load your user profile: {error}
          </div>
        ) : (
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        )}
      </main>
    </>
  )
}
