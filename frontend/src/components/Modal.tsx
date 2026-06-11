import { useEffect, useId, useRef } from 'react'

interface ModalProps {
  title: string
  onClose: () => void
  children: React.ReactNode
  /** Optional max-width override, e.g. '720px' for wide forms. */
  maxWidth?: string
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export default function Modal({ title, onClose, children, maxWidth }: ModalProps) {
  const ref = useRef<HTMLDivElement>(null)
  const titleId = useId()

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const node = ref.current
    const first = node?.querySelector<HTMLElement>(FOCUSABLE)
    ;(first ?? node)?.focus()

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key !== 'Tab' || !node) return
      const focusables = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (focusables.length === 0) return
      const firstEl = focusables[0]
      const lastEl = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === firstEl) {
        e.preventDefault()
        lastEl.focus()
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault()
        firstEl.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previous?.focus()
    }
  }, [onClose])

  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={ref}
        tabIndex={-1}
        style={maxWidth ? { maxWidth } : undefined}
      >
        <h2 id={titleId}>{title}</h2>
        {children}
      </div>
    </div>
  )
}
