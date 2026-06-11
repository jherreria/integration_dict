import { useId, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../../api/client'
import { createIntegration } from '../../api/integrations'
import type { Status } from '../../api/types'
import Modal from '../../components/Modal'
import { STATUS_LABELS } from '../../components/StatusBadge'
import { useToast } from '../../context/ToastContext'
import { ALL_STATUSES } from './Filters'

export default function CreateIntegrationModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const baseId = useId()

  const [name, setName] = useState('')
  const [status, setStatus] = useState<Status>('planning')
  const [description, setDescription] = useState('')
  const [pending, setPending] = useState(false)
  const [nameError, setNameError] = useState<string | null>(null)

  const nameId = `${baseId}-name`
  const nameErrorId = `${baseId}-name-error`
  const statusId = `${baseId}-status`
  const descriptionId = `${baseId}-description`

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      setNameError('Name is required.')
      return
    }
    setNameError(null)
    setPending(true)
    try {
      const created = await createIntegration({ name: trimmed, status, description })
      toast(`Integration “${created.name}” created.`, 'success')
      navigate(`/integrations/${created.id}`, { state: { edit: true } })
    } catch (err) {
      setPending(false)
      if (err instanceof ApiError && err.status === 409) {
        setNameError(err.detail)
      } else if (err instanceof Error) {
        toast(err.message, 'error')
      }
    }
  }

  return (
    <Modal title="Add Integration" onClose={onClose}>
      <form onSubmit={handleSubmit} noValidate>
        <div style={{ display: 'grid', gap: 12 }}>
          <div>
            <label htmlFor={nameId}>Name</label>
            <input
              id={nameId}
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                setNameError(null)
              }}
              required
              autoFocus
              disabled={pending}
              aria-invalid={nameError ? true : undefined}
              aria-describedby={nameError ? nameErrorId : undefined}
            />
            {nameError && (
              <p className="field-error" id={nameErrorId} role="alert">
                {nameError}
              </p>
            )}
          </div>
          <div>
            <label htmlFor={statusId}>Status</label>
            <select
              id={statusId}
              value={status}
              onChange={(e) => setStatus(e.target.value as Status)}
              disabled={pending}
            >
              {ALL_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABELS[s]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor={descriptionId}>Description</label>
            <textarea
              id={descriptionId}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={pending}
            />
          </div>
        </div>
        <div className="modal-actions">
          <button type="button" className="btn secondary" onClick={onClose} disabled={pending}>
            Cancel
          </button>
          <button type="submit" className="btn" disabled={pending}>
            {pending ? 'Creating…' : 'Create'}
          </button>
        </div>
      </form>
    </Modal>
  )
}
