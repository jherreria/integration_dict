import { Component } from 'react'

interface ErrorBoundaryProps {
  children: React.ReactNode
  fallback?: React.ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        this.props.fallback ?? (
          <div className="error-note" role="alert">
            <strong>Something went wrong.</strong> {this.state.error.message}{' '}
            <button type="button" className="btn link" onClick={() => window.location.reload()}>
              Reload
            </button>
          </div>
        )
      )
    }
    return this.props.children
  }
}
