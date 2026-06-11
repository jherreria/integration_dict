import { createContext, useCallback, useContext, useRef, useState } from 'react'

type ToastKind = 'info' | 'success' | 'error'

interface Toast {
  id: number
  kind: ToastKind
  message: string
}

interface ToastContextValue {
  toast: (message: string, kind?: ToastKind) => void
}

const ToastContext = createContext<ToastContextValue>({ toast: () => undefined })

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const toast = useCallback((message: string, kind: ToastKind = 'info') => {
    const id = nextId.current++
    setToasts((prev) => [...prev.slice(-3), { id, kind, message }])
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, kind === 'error' ? 8000 : 4000)
  }, [])

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
