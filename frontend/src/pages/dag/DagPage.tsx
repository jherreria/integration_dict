// Dependency graph page. Focal mode (/integrations/:id/dag) shows the
// neighborhood of one integration with a depth control; global mode (/dag)
// shows the whole graph.

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getGlobalGraph, getIntegrationGraph } from '../../api/integrations'
import type { GraphPayload } from '../../api/types'
import EmptyState from '../../components/EmptyState'
import ErrorBoundary from '../../components/ErrorBoundary'
import Spinner from '../../components/Spinner'
import { useToast } from '../../context/ToastContext'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import FlowGraph from './FlowGraph'

type Depth = 1 | 2 | 3 | 'all'

export default function DagPage() {
  const { id } = useParams()
  const { toast } = useToast()
  const [depth, setDepth] = useState<Depth>(2)
  const [payload, setPayload] = useState<GraphPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const rootName = id ? payload?.nodes.find((n) => n.is_root)?.name : undefined
  useDocumentTitle(
    id ? `Dependency graph${rootName ? ` — ${rootName}` : ''}` : 'Integration dependency graph',
  )

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    const fetchGraph = id
      ? getIntegrationGraph(id, depth, controller.signal)
      : getGlobalGraph(controller.signal)
    fetchGraph
      .then((data) => {
        setPayload(data)
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        const message = err instanceof Error ? err.message : 'Failed to load the dependency graph.'
        setError(message)
        setLoading(false)
        toast(message, 'error')
      })
    return () => controller.abort()
  }, [id, depth, toast])

  return (
    <div>
      <div className="page-head">
        <h1>{id ? `Dependency graph — ${rootName ?? '…'}` : 'Integration dependency graph'}</h1>
        <span className="spacer" />
        {id && (
          <>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              Depth
              <select
                value={String(depth)}
                onChange={(e) => {
                  const v = e.target.value
                  setDepth(v === 'all' ? 'all' : (Number(v) as 1 | 2 | 3))
                }}
                style={{ width: 'auto' }}
              >
                <option value="1">1</option>
                <option value="2">2</option>
                <option value="3">3</option>
                <option value="all">All</option>
              </select>
            </label>
            <Link to={`/integrations/${id}`}>← Back to integration</Link>
          </>
        )}
      </div>

      {loading ? (
        <Spinner label="Loading graph…" />
      ) : error ? (
        <div className="error-note" role="alert">
          {error}
        </div>
      ) : payload && payload.nodes.length === 0 ? (
        <EmptyState title="Nothing to show — add upstream/downstream/integrated relationships first" />
      ) : payload ? (
        <ErrorBoundary>
          <FlowGraph payload={payload} />
        </ErrorBoundary>
      ) : null}
    </div>
  )
}
