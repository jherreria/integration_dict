import { Link } from 'react-router-dom'
import EmptyState from '../components/EmptyState'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

export default function NotFoundPage() {
  useDocumentTitle('Not found')
  return (
    <EmptyState title="Page not found">
      <p>
        <Link to="/">Back to the integration list</Link>
      </p>
    </EmptyState>
  )
}
