import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { listIntegrations } from '../../api/integrations'
import { getSearchStatus } from '../../api/lookups'
import type { IntegrationListItem, Page, SearchMode, Status } from '../../api/types'
import EmptyState from '../../components/EmptyState'
import Pagination from '../../components/Pagination'
import Spinner from '../../components/Spinner'
import { useToast } from '../../context/ToastContext'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import CreateIntegrationModal from './CreateIntegrationModal'
import Filters, { ALL_STATUSES } from './Filters'
import IntegrationsTable, { type SortKey } from './IntegrationsTable'
import SearchBox from './SearchBox'

const AI_PREF_KEY = 'idict.aiSearch'

function isStatus(value: string): value is Status {
  return (ALL_STATUSES as string[]).includes(value)
}

function readAiPreference(): boolean {
  try {
    return localStorage.getItem(AI_PREF_KEY) !== '0'
  } catch {
    return true
  }
}

function writeAiPreference(on: boolean) {
  try {
    localStorage.setItem(AI_PREF_KEY, on ? '1' : '0')
  } catch {
    // Storage may be unavailable; the URL param still carries the choice.
  }
}

export default function IntegrationsPage() {
  useDocumentTitle('Integrations')
  const { toast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()

  // ---- list state, derived from the URL ----
  const q = searchParams.get('q') ?? ''
  const statusParam = searchParams.get('status') ?? ''
  const statuses = useMemo(
    () => statusParam.split(',').filter(isStatus),
    [statusParam],
  )
  const type = searchParams.get('type') ?? ''
  const tag = searchParams.get('tag') ?? ''
  const system = searchParams.get('system') ?? ''
  const sort = searchParams.get('sort') ?? ''
  const order: 'asc' | 'desc' = searchParams.get('order') === 'desc' ? 'desc' : 'asc'
  const page = Math.max(1, Number.parseInt(searchParams.get('page') ?? '1', 10) || 1)
  const aiParam = searchParams.get('ai')
  // ai=0 in the URL opts out of AI search; otherwise fall back to the stored preference.
  const aiOn = aiParam !== null ? aiParam !== '0' : readAiPreference()

  const debouncedQ = useDebouncedValue(q, 350)

  // ---- server state ----
  const [data, setData] = useState<Page<IntegrationListItem> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // null = /search/status not resolved yet
  const [searchConfigured, setSearchConfigured] = useState<boolean | null>(null)
  // Whether the request that produced `data` asked for AI ranking.
  const [aiRequested, setAiRequested] = useState(false)
  const [showCreate, setShowCreate] = useState(false)

  useEffect(() => {
    let cancelled = false
    getSearchStatus()
      .then((s) => {
        if (!cancelled) setSearchConfigured(s.endpoint_configured)
      })
      .catch(() => {
        if (!cancelled) setSearchConfigured(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const aiActive = searchConfigured === true && aiOn
  const mode: SearchMode | undefined = debouncedQ ? (aiActive ? 'ai' : 'keyword') : undefined

  useEffect(() => {
    // Wait until we know whether AI search is available, so the first
    // searched request is sent with the right mode.
    if (searchConfigured === null) return
    const controller = new AbortController()
    setLoading(true)
    listIntegrations(
      {
        q: debouncedQ || undefined,
        mode,
        status: statuses.length > 0 ? statuses : undefined,
        type: type || undefined,
        tag: tag || undefined,
        system: system || undefined,
        sort: sort || undefined,
        order: sort ? order : undefined,
        page,
      },
      controller.signal,
    )
      .then((result) => {
        setData(result)
        setAiRequested(mode === 'ai')
        setError(null)
        setLoading(false)
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        const message = err instanceof Error ? err.message : 'Request failed'
        setError(message)
        setLoading(false)
        toast(message, 'error')
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchConfigured, debouncedQ, mode, statusParam, type, tag, system, sort, order, page, toast])

  // ---- URL updates (any filter change resets page to 1) ----
  const updateParams = useCallback(
    (
      changes: Record<string, string | null>,
      opts?: { resetPage?: boolean; replace?: boolean },
    ) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [key, value] of Object.entries(changes)) {
            if (value === null || value === '') next.delete(key)
            else next.set(key, value)
          }
          if (opts?.resetPage !== false) next.delete('page')
          return next
        },
        { replace: opts?.replace ?? false },
      )
    },
    [setSearchParams],
  )

  const handleSearchChange = (value: string) => updateParams({ q: value }, { replace: true })

  const toggleAi = () => {
    const next = !aiOn
    writeAiPreference(next)
    updateParams({ ai: next ? null : '0' })
  }

  const handleSort = (key: SortKey) => {
    if (sort === key) updateParams({ order: order === 'asc' ? 'desc' : 'asc' })
    else updateParams({ sort: key, order: 'asc' })
  }

  const clearFilters = () =>
    updateParams({ status: null, type: null, tag: null, system: null })

  const handlePageChange = (p: number) =>
    updateParams({ page: p <= 1 ? null : String(p) }, { resetPage: false })

  // ---- render ----
  const aiRanked = data?.search_mode_used === 'ai'
  const anyFilterOrSearch =
    debouncedQ !== '' || statuses.length > 0 || type !== '' || tag !== '' || system !== ''

  let resultsLine: string | null = null
  if (data && !error) {
    if (data.search_mode_used === 'ai') {
      resultsLine = `${data.total} results, ranked by relevance`
    } else if (data.search_mode_used === 'keyword' && aiRequested) {
      resultsLine = `${data.total} results (keyword fallback)`
    } else {
      resultsLine = `${data.total} results`
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Integrations</h1>
        <span className="spacer" />
        <button type="button" className="btn" onClick={() => setShowCreate(true)}>
          Add Integration
        </button>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <SearchBox
          value={q}
          onChange={handleSearchChange}
          loading={loading}
          aiAvailable={searchConfigured === true}
          aiOn={aiOn}
          onToggleAi={toggleAi}
        />
        <Filters
          statuses={statuses}
          type={type}
          tag={tag}
          system={system}
          onStatusesChange={(next) => updateParams({ status: next.join(',') })}
          onTypeChange={(next) => updateParams({ type: next })}
          onTagChange={(next) => updateParams({ tag: next })}
          onSystemChange={(next) => updateParams({ system: next })}
          onClear={clearFilters}
        />
      </div>

      {error && (
        <div className="error-note" role="alert">
          {error}
        </div>
      )}

      {data === null && !error && (
        <p>
          <Spinner label="Loading integrations…" />
        </p>
      )}

      {data && data.items.length === 0 && !error && (
        anyFilterOrSearch ? (
          <EmptyState title="No matches">
            <p>Try adjusting your search or clearing the filters.</p>
          </EmptyState>
        ) : (
          <EmptyState title="No integrations yet">
            <p>Use the “Add Integration” button to create the first one.</p>
          </EmptyState>
        )
      )}

      {data && data.items.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'auto' }}>
          <IntegrationsTable
            items={data.items}
            sort={sort}
            order={order}
            sortDisabled={aiRanked}
            onSort={handleSort}
          />
        </div>
      )}

      {resultsLine !== null && (
        <p className="muted" role="status">
          {resultsLine}
        </p>
      )}

      {data && (
        <Pagination
          page={data.page}
          pageSize={data.page_size}
          total={data.total}
          onPageChange={handlePageChange}
        />
      )}

      {showCreate && <CreateIntegrationModal onClose={() => setShowCreate(false)} />}
    </>
  )
}
