// Integration detail page: read view + in-place metadata editing with
// per-field RBAC, optimistic-concurrency saves, dirty-navigation guards,
// admin delete, and the audit history panel.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useBlocker, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../../api/client'
import {
  deleteIntegration,
  getIntegration,
  listIntegrations,
  updateIntegration,
} from '../../api/integrations'
import {
  getCredentialTypes,
  getEnums,
  getSystems,
  getTags,
  getTypes,
  getUsers,
} from '../../api/lookups'
import type { IntegrationDetail } from '../../api/types'
import ConfirmDialog from '../../components/ConfirmDialog'
import EmptyState from '../../components/EmptyState'
import Spinner from '../../components/Spinner'
import StatusBadge from '../../components/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { useUser } from '../../context/UserContext'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { formatDateTime } from '../../utils/format'
import AuditHistoryPanel from './AuditHistoryPanel'
import CommentsPanel from './CommentsPanel'
import type { EditOptions } from './fields'
import Sections from './Sections'
import { useIntegrationForm } from './useIntegrationForm'

const OPTION_PAGE_SIZE = 200

// The relationship pickers need every active integration, but the list
// endpoint caps page_size at 200 — page through until we have them all.
async function fetchAllIntegrationOptions(): Promise<{ value: string; label: string }[]> {
  const out: { value: string; label: string }[] = []
  let page = 1
  for (;;) {
    const res = await listIntegrations({ page, page_size: OPTION_PAGE_SIZE, sort: 'name', order: 'asc' })
    out.push(...res.items.map((i) => ({ value: i.id, label: i.name })))
    if (out.length >= res.total || res.items.length === 0) break
    page += 1
  }
  return out
}

export default function IntegrationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [detail, setDetail] = useState<IntegrationDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    const controller = new AbortController()
    setDetail(null)
    setLoading(true)
    setNotFound(false)
    setLoadError(null)
    getIntegration(id, controller.signal)
      .then(setDetail)
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return
        if (err instanceof ApiError && err.status === 404) setNotFound(true)
        else setLoadError(err instanceof Error ? err.message : 'Failed to load integration')
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [id])

  if (notFound) {
    return (
      <EmptyState title="Integration not found">
        <p>
          <Link to="/">Back to the integration list</Link>
        </p>
      </EmptyState>
    )
  }
  if (loadError) {
    return (
      <div className="error-note" role="alert">
        {loadError}
      </div>
    )
  }
  if (loading || !detail) {
    return (
      <p className="muted">
        <Spinner label="Loading integration" /> Loading…
      </p>
    )
  }
  return <LoadedDetail key={detail.id} detail={detail} onDetail={setDetail} />
}

function LoadedDetail({
  detail,
  onDetail,
}: {
  detail: IntegrationDetail
  onDetail: (d: IntegrationDetail) => void
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const { toast } = useToast()
  const { isAdmin } = useUser()
  const form = useIntegrationForm(detail)

  const [editing, setEditing] = useState<boolean>(
    () => Boolean((location.state as { edit?: boolean } | null)?.edit),
  )
  const [options, setOptions] = useState<EditOptions | null>(null)
  const [optionsError, setOptionsError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [auditRefresh, setAuditRefresh] = useState(0)
  // Lets programmatic navigation (post-delete) bypass the dirty-form blocker.
  const skipBlockRef = useRef(false)

  useDocumentTitle(detail.name)

  // Load edit-mode option lists once, on first entering edit mode.
  useEffect(() => {
    if (!editing || options) return
    let cancelled = false
    setOptionsError(null)
    Promise.all([
      getTags(),
      getSystems(),
      getTypes(),
      getCredentialTypes(),
      getUsers('integration'),
      getEnums(),
      fetchAllIntegrationOptions(),
    ])
      .then(([tags, systems, types, credentialTypes, users, enums, integrationOpts]) => {
        if (cancelled) return
        // Merge in this integration's existing relationship targets so their
        // chips always resolve to a name even if they fall outside the list.
        const merged = new Map(integrationOpts.map((o) => [o.value, o]))
        for (const ref of [...detail.upstream, ...detail.downstream, ...detail.integrated]) {
          if (!merged.has(ref.id)) merged.set(ref.id, { value: ref.id, label: ref.name })
        }
        setOptions({
          tags: tags.map((t) => ({ value: t.name, label: t.name })),
          systems: systems.map((s) => ({ value: s.name, label: s.name })),
          typeNames: types.map((t) => t.name),
          credentialTypeNames: credentialTypes.map((c) => c.name),
          integrations: [...merged.values()],
          users,
          statuses: enums.statuses,
          levels: enums.levels,
        })
      })
      .catch((err: Error) => {
        if (!cancelled) setOptionsError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [editing, options, detail])

  // Guard client-side navigation away from a dirty edit form.
  const shouldBlock = useCallback(
    () => editing && form.dirty && !skipBlockRef.current,
    [editing, form.dirty],
  )
  const blocker = useBlocker(shouldBlock)

  // Guard full page unloads (refresh, tab close) too.
  useEffect(() => {
    if (!(editing && form.dirty)) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [editing, form.dirty])

  async function save() {
    setSaving(true)
    try {
      const updated = await updateIntegration(detail.id, form.buildPatch())
      onDetail(updated)
      setEditing(false)
      setAuditRefresh((n) => n + 1)
      toast('Integration saved.', 'success')
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          toast(err.detail, 'error')
          if (err.fields?.length) {
            form.setFieldErrors(
              Object.fromEntries(err.fields.map((f) => [f, 'Integration team only'])),
            )
          }
        } else if (err.status === 409) {
          // 409 covers both a duplicate name and a concurrent-edit version
          // clash; only the latter is fixed by reloading.
          const isVersionConflict = /modified by someone else/i.test(err.detail)
          toast(
            isVersionConflict
              ? `${err.detail} Reload the page to pick up the latest version.`
              : err.detail,
            'error',
          )
        } else {
          toast(err.detail, 'error')
        }
      } else if (err instanceof Error) {
        toast(err.message, 'error')
      }
    } finally {
      setSaving(false)
    }
  }

  function cancelEdit() {
    if (form.dirty) setConfirmDiscard(true)
    else setEditing(false)
  }

  async function doDelete() {
    setDeleting(true)
    try {
      await deleteIntegration(detail.id)
      skipBlockRef.current = true
      setAuditRefresh((n) => n + 1)
      toast(`“${detail.name}” deleted.`, 'success')
      navigate('/')
    } catch (err) {
      setDeleting(false)
      setConfirmDelete(false)
      if (err instanceof ApiError) toast(err.detail, 'error')
      else if (err instanceof Error) toast(err.message, 'error')
    }
  }

  const optionsReady = options !== null

  return (
    <>
      <div className="page-head">
        <h1>{detail.name}</h1>
        <StatusBadge status={detail.status} />
        <span className="spacer" />
        <Link className="btn secondary" to={`/integrations/${detail.id}/dag`}>
          View DAG
        </Link>
        {!editing && (
          <button type="button" className="btn" onClick={() => setEditing(true)}>
            Edit
          </button>
        )}
        {isAdmin && (
          <button type="button" className="btn danger" onClick={() => setConfirmDelete(true)}>
            Delete
          </button>
        )}
      </div>

      <p className="muted" style={{ margin: '0 0 16px' }}>
        Created {formatDateTime(detail.created_at)} by {detail.created_by ?? '—'} · Updated{' '}
        {formatDateTime(detail.updated_at)} by {detail.updated_by ?? '—'} · Version {detail.version}
      </p>

      {editing && optionsError && (
        <div className="error-note" role="alert">
          Could not load editing options: {optionsError}
        </div>
      )}
      {editing && !optionsReady && !optionsError ? (
        <p className="muted">
          <Spinner label="Loading editing options" /> Preparing edit form…
        </p>
      ) : (
        <Sections
          detail={detail}
          editing={editing && optionsReady}
          draft={form.draft}
          set={form.set}
          options={options}
          fieldErrors={form.fieldErrors}
        />
      )}

      {editing && (
        <div
          className="card"
          style={{
            position: 'sticky',
            bottom: 12,
            zIndex: 50,
            marginTop: 16,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <span className="muted" aria-live="polite">
            {form.dirty
              ? `${form.changedCount} field${form.changedCount === 1 ? '' : 's'} changed`
              : 'No changes yet'}
          </span>
          <span style={{ flex: 1 }} />
          <button type="button" className="btn secondary" onClick={cancelEdit} disabled={saving}>
            Cancel
          </button>
          <button
            type="button"
            className="btn green"
            onClick={() => void save()}
            disabled={!form.dirty || saving}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      )}

      <CommentsPanel integrationId={detail.id} onPosted={() => setAuditRefresh((n) => n + 1)} />

      <AuditHistoryPanel integrationId={detail.id} refreshKey={auditRefresh} />

      {confirmDiscard && (
        <ConfirmDialog
          title="Discard changes?"
          message={`Discard ${form.changedCount} unsaved change${form.changedCount === 1 ? '' : 's'}?`}
          confirmLabel="Discard"
          danger
          onConfirm={() => {
            form.reset()
            setEditing(false)
            setConfirmDiscard(false)
          }}
          onCancel={() => setConfirmDiscard(false)}
        />
      )}

      {blocker.state === 'blocked' && (
        <ConfirmDialog
          title="Discard changes?"
          message="You have unsaved changes. Leave this page and discard them?"
          confirmLabel="Leave page"
          danger
          onConfirm={() => {
            form.reset()
            blocker.proceed()
          }}
          onCancel={() => blocker.reset()}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Delete integration"
          message={
            <>
              Delete <strong>{detail.name}</strong>? This cannot be undone from the UI. The audit
              history is retained.
            </>
          }
          confirmLabel="Delete"
          danger
          busy={deleting}
          onConfirm={() => void doDelete()}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </>
  )
}
