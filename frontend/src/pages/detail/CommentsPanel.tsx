// Append-only comment / tech-note thread for an integration. Any user can add
// notes and image/screenshot attachments; they cannot be edited or deleted.
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { addComment, attachmentUrl, getComments } from '../../api/integrations'
import type { Comment } from '../../api/types'
import EmptyState from '../../components/EmptyState'
import Pagination from '../../components/Pagination'
import Spinner from '../../components/Spinner'
import { useToast } from '../../context/ToastContext'
import { formatDateTime } from '../../utils/format'

const PAGE_SIZE = 25
const MAX_FILES = 10
const MAX_BYTES = 5 * 1024 * 1024
const ACCEPTED = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']

interface CommentsPanelProps {
  integrationId: string
  /** Called after a comment posts so the audit panel can refresh. */
  onPosted?: () => void
}

interface Pending {
  id: string
  file: File
  url: string // object URL for the local preview
}

export default function CommentsPanel({ integrationId, onPosted }: CommentsPanelProps) {
  const { toast } = useToast()
  const [items, setItems] = useState<Comment[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState<Pending[]>([])
  const [posting, setPosting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const seq = useRef(0)

  const load = useCallback(
    (p: number) => {
      setLoading(true)
      getComments(integrationId, p, PAGE_SIZE)
        .then((res) => {
          setItems(res.items)
          setTotal(res.total)
          setPage(res.page)
        })
        .catch((err: unknown) => {
          if (err instanceof Error) toast(err.message, 'error')
        })
        .finally(() => setLoading(false))
    },
    [integrationId, toast],
  )

  useEffect(() => {
    load(1)
  }, [load])

  // Revoke object URLs when previews are discarded / on unmount.
  useEffect(() => () => pending.forEach((p) => URL.revokeObjectURL(p.url)), [pending])

  const addFiles = useCallback(
    (incoming: File[]) => {
      const images = incoming.filter((f) => ACCEPTED.includes(f.type))
      const rejectedType = incoming.length - images.length
      if (rejectedType > 0) toast('Only PNG, JPEG, GIF, or WEBP images can be attached.', 'error')
      setPending((prev) => {
        const next = [...prev]
        for (const file of images) {
          if (next.length >= MAX_FILES) {
            toast(`At most ${MAX_FILES} images per comment.`, 'error')
            break
          }
          if (file.size > MAX_BYTES) {
            toast(`"${file.name}" is larger than 5 MB.`, 'error')
            continue
          }
          next.push({ id: `p${seq.current++}`, file, url: URL.createObjectURL(file) })
        }
        return next
      })
    },
    [toast],
  )

  function removePending(id: string) {
    setPending((prev) => {
      const target = prev.find((p) => p.id === id)
      if (target) URL.revokeObjectURL(target.url)
      return prev.filter((p) => p.id !== id)
    })
  }

  function onPaste(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const files = Array.from(e.clipboardData.files)
    if (files.length) {
      e.preventDefault()
      addFiles(files)
    }
  }

  async function submit() {
    const body = draft.trim()
    if (!body && pending.length === 0) return
    setPosting(true)
    try {
      await addComment(integrationId, body, pending.map((p) => p.file))
      setDraft('')
      pending.forEach((p) => URL.revokeObjectURL(p.url))
      setPending([])
      load(1) // newest first — jump back to the first page to show it
      onPosted?.()
      toast('Comment added.', 'success')
    } catch (err) {
      if (err instanceof ApiError) toast(err.detail, 'error')
      else if (err instanceof Error) toast(err.message, 'error')
    } finally {
      setPosting(false)
    }
  }

  return (
    <section className="card" style={{ marginTop: 16 }} aria-labelledby="comments-heading">
      <h2 id="comments-heading">Comments &amp; tech notes</h2>

      <div style={{ marginBottom: 16 }}>
        <label htmlFor="new-comment" className="sr-only">
          Add a comment
        </label>
        <textarea
          id="new-comment"
          rows={3}
          value={draft}
          placeholder="Add a note, gotcha, or hand-off detail. Paste a screenshot or attach images. (Cannot be deleted once posted.)"
          onChange={(e) => setDraft(e.target.value)}
          onPaste={onPaste}
          disabled={posting}
        />

        {pending.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
            {pending.map((p) => (
              <div
                key={p.id}
                style={{ position: 'relative', width: 88, height: 88 }}
                title={p.file.name}
              >
                <img
                  src={p.url}
                  alt={p.file.name}
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--color-border-strong)',
                  }}
                />
                <button
                  type="button"
                  className="btn small danger"
                  aria-label={`Remove ${p.file.name}`}
                  onClick={() => removePending(p.id)}
                  style={{ position: 'absolute', top: -8, right: -8, padding: '0 7px', borderRadius: 999 }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED.join(',')}
          multiple
          style={{ display: 'none' }}
          onChange={(e) => {
            addFiles(Array.from(e.target.files ?? []))
            e.target.value = '' // allow re-selecting the same file
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
          <button
            type="button"
            className="btn secondary small"
            onClick={() => fileInputRef.current?.click()}
            disabled={posting}
          >
            Attach image
          </button>
          <span className="muted" style={{ fontSize: '12px' }}>
            or paste a screenshot · PNG/JPEG/GIF/WEBP · up to 5 MB each
          </span>
          <span style={{ flex: 1 }} />
          <button
            type="button"
            className="btn"
            onClick={() => void submit()}
            disabled={posting || (draft.trim().length === 0 && pending.length === 0)}
          >
            {posting ? 'Adding…' : 'Add comment'}
          </button>
        </div>
      </div>

      {loading ? (
        <p className="muted">
          <Spinner label="Loading comments" /> Loading comments…
        </p>
      ) : items.length === 0 ? (
        <EmptyState title="No comments yet">
          <p className="muted">Be the first to add a note.</p>
        </EmptyState>
      ) : (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {items.map((c) => (
            <li key={c.id} style={{ borderTop: '1px solid var(--color-border)', paddingTop: 12 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
                <strong>{c.author_name || c.author_email}</strong>
                <span className="muted" style={{ fontSize: '12.5px' }}>
                  {formatDateTime(c.created_at)}
                </span>
              </div>
              {c.body && <p style={{ whiteSpace: 'pre-wrap', margin: '4px 0 0' }}>{c.body}</p>}
              {c.attachments.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                  {c.attachments.map((a) => {
                    const url = attachmentUrl(integrationId, c.id, a.id)
                    return (
                      <a key={a.id} href={url} target="_blank" rel="noreferrer" title={a.filename}>
                        <img
                          src={url}
                          alt={a.filename}
                          loading="lazy"
                          style={{
                            maxWidth: 200,
                            maxHeight: 200,
                            borderRadius: 'var(--radius-sm)',
                            border: '1px solid var(--color-border)',
                            display: 'block',
                          }}
                        />
                      </a>
                    )
                  })}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPageChange={load} />
    </section>
  )
}
