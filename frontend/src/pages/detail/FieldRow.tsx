// One labelled row of the detail page: read-only rendering in view mode,
// the matching input (per the field registry `kind`) in edit mode, with
// per-field RBAC locking and inline validation errors.
import { useId } from 'react'
import { Link } from 'react-router-dom'
import type { IntegrationDetail, IntegrationRef, Level, Status, UserOut } from '../../api/types'
import LockHint from '../../components/LockHint'
import MultiSelectCreatable from '../../components/MultiSelectCreatable'
import StatusBadge, { STATUS_LABELS } from '../../components/StatusBadge'
import { useUser } from '../../context/UserContext'
import { formatDate } from '../../utils/format'
import type { EditOptions, FieldDef } from './fields'
import type { FormValues } from './useIntegrationForm'

const EM_DASH = '—'

interface FieldRowProps {
  def: FieldDef
  detail: IntegrationDetail
  editing: boolean
  draft: FormValues
  set: <K extends keyof FormValues>(field: K, value: FormValues[K]) => void
  options: EditOptions | null
  error?: string
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

// Only http(s) URLs are safe to render as a clickable link. Anything else
// (javascript:, data:, …) is shown as plain text to prevent stored XSS.
function safeHttpUrl(raw: string): string | null {
  try {
    const url = new URL(raw, window.location.origin)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}

function Chips({ values, system = false }: { values: string[]; system?: boolean }) {
  if (values.length === 0) return <>{EM_DASH}</>
  return (
    <>
      {values.map((v) => (
        <span key={v} className={`chip${system ? ' system' : ''}`}>
          {v}
        </span>
      ))}
    </>
  )
}

function RefLinks({ refs }: { refs: IntegrationRef[] }) {
  if (refs.length === 0) return <>{EM_DASH}</>
  return (
    <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
      {refs.map((r) => (
        <li key={r.id}>
          <Link to={`/integrations/${r.id}`}>{r.name}</Link>{' '}
          <StatusBadge status={r.status as Status} />
        </li>
      ))}
    </ul>
  )
}

function userLabel(u: UserOut): string {
  return u.display_name ? `${u.display_name} (${u.email})` : u.email
}

function viewValue(def: FieldDef, detail: IntegrationDetail): React.ReactNode {
  switch (def.kind) {
    case 'text': {
      const v = detail[def.key as 'name' | 'associated_projects' | 'account_used' | 'needed_roles']
      return v ? v : EM_DASH
    }
    case 'textarea': {
      const v = detail[def.key as 'description' | 'notes']
      return v ? <span style={{ whiteSpace: 'pre-wrap' }}>{v}</span> : EM_DASH
    }
    case 'url': {
      if (!detail.documentation_url) return EM_DASH
      const safe = safeHttpUrl(detail.documentation_url)
      return safe ? (
        <a href={safe} target="_blank" rel="noreferrer">
          {detail.documentation_url}
        </a>
      ) : (
        // Non-http(s) value: render as plain text, never as a link.
        <span>{detail.documentation_url}</span>
      )
    }
    case 'status':
      return <StatusBadge status={detail.status} />
    case 'level': {
      const v = detail[def.key as 'complexity' | 'business_logic']
      return v ? capitalize(v) : EM_DASH
    }
    case 'lookup-type':
      return detail.type ?? EM_DASH
    case 'lookup-credential':
      return detail.credential_type ?? EM_DASH
    case 'tags':
      return <Chips values={detail.tags} />
    case 'systems-multi':
      return <Chips values={detail[def.key as 'sources' | 'targets']} system />
    case 'integrations-multi':
      return <RefLinks refs={detail[def.key as 'upstream' | 'downstream' | 'integrated']} />
    case 'boolean-approval':
      return detail[def.key as 'design_approved' | 'code_approved'] ? 'Approved' : 'Not approved'
    case 'user-select': {
      const approver = def.key === 'design_approver_id' ? detail.design_approver : detail.code_approver
      return approver ? approver.display_name || approver.email : EM_DASH
    }
    case 'date':
      return formatDate(detail[def.key as 'design_approval_date' | 'code_approval_date'])
  }
}

function EditControl({
  def,
  detail,
  draft,
  set,
  options,
  canEdit,
  controlId,
  errorId,
}: {
  def: FieldDef
  detail: IntegrationDetail
  draft: FormValues
  set: FieldRowProps['set']
  options: EditOptions | null
  canEdit: boolean
  controlId: string
  errorId?: string
}) {
  const listId = `${controlId}-list`
  const disabled = !canEdit

  switch (def.kind) {
    case 'text': {
      const key = def.key as 'name' | 'associated_projects' | 'account_used' | 'needed_roles'
      return (
        <input
          id={controlId}
          type="text"
          value={draft[key]}
          onChange={(e) => set(key, e.target.value)}
          disabled={disabled}
          aria-describedby={errorId}
        />
      )
    }
    case 'textarea': {
      const key = def.key as 'description' | 'notes'
      return (
        <textarea
          id={controlId}
          rows={4}
          value={draft[key]}
          onChange={(e) => set(key, e.target.value)}
          disabled={disabled}
          aria-describedby={errorId}
        />
      )
    }
    case 'url':
      return (
        <input
          id={controlId}
          type="url"
          value={draft.documentation_url}
          onChange={(e) => set('documentation_url', e.target.value)}
          disabled={disabled}
          placeholder="https://…"
          aria-describedby={errorId}
        />
      )
    case 'status':
      return (
        <select
          id={controlId}
          value={draft.status}
          onChange={(e) => set('status', e.target.value as Status)}
          disabled={disabled}
          aria-describedby={errorId}
        >
          {(options?.statuses ?? []).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s] ?? s}
            </option>
          ))}
        </select>
      )
    case 'level': {
      const key = def.key as 'complexity' | 'business_logic'
      return (
        <select
          id={controlId}
          value={draft[key] ?? ''}
          onChange={(e) => set(key, e.target.value === '' ? null : (e.target.value as Level))}
          disabled={disabled}
          aria-describedby={errorId}
        >
          <option value="">{EM_DASH}</option>
          {(options?.levels ?? []).map((l) => (
            <option key={l} value={l}>
              {capitalize(l)}
            </option>
          ))}
        </select>
      )
    }
    case 'lookup-type':
    case 'lookup-credential': {
      // Creatable single value: free-text input backed by a datalist of the
      // existing lookup names (typing a new name creates it server-side).
      const key = def.kind === 'lookup-type' ? ('type' as const) : ('credential_type' as const)
      const names = def.kind === 'lookup-type' ? options?.typeNames : options?.credentialTypeNames
      return (
        <>
          <input
            id={controlId}
            type="text"
            list={listId}
            value={draft[key] ?? ''}
            onChange={(e) => set(key, e.target.value === '' ? null : e.target.value)}
            disabled={disabled}
            placeholder="Pick or type a new one…"
            aria-describedby={errorId}
          />
          <datalist id={listId}>
            {(names ?? []).map((n) => (
              <option key={n} value={n} />
            ))}
          </datalist>
        </>
      )
    }
    case 'tags':
      return (
        <MultiSelectCreatable
          inputId={controlId}
          values={draft.tags}
          options={options?.tags ?? []}
          onChange={(values) => set('tags', values)}
          creatable
          disabled={disabled}
        />
      )
    case 'systems-multi': {
      const key = def.key as 'sources' | 'targets'
      return (
        <MultiSelectCreatable
          inputId={controlId}
          values={draft[key]}
          options={options?.systems ?? []}
          onChange={(values) => set(key, values)}
          creatable
          disabled={disabled}
        />
      )
    }
    case 'integrations-multi': {
      const key = def.key as 'upstream' | 'downstream' | 'integrated'
      return (
        <MultiSelectCreatable
          inputId={controlId}
          values={draft[key]}
          options={options?.integrations ?? []}
          onChange={(values) => set(key, values)}
          excludeValues={[detail.id]}
          disabled={disabled}
        />
      )
    }
    case 'boolean-approval': {
      const key = def.key as 'design_approved' | 'code_approved'
      const approverKey = key === 'design_approved' ? 'design_approver_id' : 'code_approver_id'
      const showDefaultHint = draft[key] && !detail[key] && !draft[approverKey]
      return (
        <>
          <input
            id={controlId}
            type="checkbox"
            checked={draft[key]}
            onChange={(e) => set(key, e.target.checked)}
            disabled={disabled}
            aria-describedby={errorId}
          />
          {showDefaultHint && (
            <p className="muted" style={{ margin: '4px 0 0', fontSize: '12.5px' }}>
              Approver and date will default to you / today.
            </p>
          )}
        </>
      )
    }
    case 'user-select': {
      const key = def.key as 'design_approver_id' | 'code_approver_id'
      return (
        <select
          id={controlId}
          value={draft[key] ?? ''}
          onChange={(e) => set(key, e.target.value === '' ? null : e.target.value)}
          disabled={disabled}
          aria-describedby={errorId}
        >
          <option value="">{EM_DASH}</option>
          {(options?.users ?? []).map((u) => (
            <option key={u.id} value={u.id}>
              {userLabel(u)}
            </option>
          ))}
        </select>
      )
    }
    case 'date': {
      const key = def.key as 'design_approval_date' | 'code_approval_date'
      return (
        <input
          id={controlId}
          type="date"
          value={draft[key] ?? ''}
          onChange={(e) => set(key, e.target.value === '' ? null : e.target.value)}
          disabled={disabled}
          aria-describedby={errorId}
        />
      )
    }
  }
}

export default function FieldRow({ def, detail, editing, draft, set, options, error }: FieldRowProps) {
  const { canEditField } = useUser()
  const controlId = useId()
  const errorId = error ? `${controlId}-error` : undefined
  const canEdit = canEditField(def.key)
  const locked = editing && !canEdit

  return (
    <div
      className="field-row"
      style={{
        display: 'grid',
        gridTemplateColumns: '200px 1fr',
        gap: '4px 16px',
        alignItems: 'start',
        padding: '7px 0',
        borderTop: '1px solid var(--color-border)',
      }}
    >
      <div style={{ paddingTop: editing ? 8 : 0 }}>
        {editing ? <label htmlFor={controlId}>{def.label}</label> : (
          <span style={{ fontWeight: 600, color: 'var(--ts-slate)' }}>{def.label}</span>
        )}{' '}
        {locked && <LockHint />}
      </div>
      <div>
        {editing ? (
          <EditControl
            def={def}
            detail={detail}
            draft={draft}
            set={set}
            options={options}
            canEdit={canEdit}
            controlId={controlId}
            errorId={errorId}
          />
        ) : (
          viewValue(def, detail)
        )}
        {error && (
          <p className="field-error" id={errorId}>
            {error}
          </p>
        )}
      </div>
    </div>
  )
}
