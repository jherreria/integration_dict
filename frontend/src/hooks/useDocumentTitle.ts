import { useEffect } from 'react'

export function useDocumentTitle(title: string | null | undefined) {
  useEffect(() => {
    document.title = title ? `${title} — Integration Dictionary` : 'Integration Dictionary'
    return () => {
      document.title = 'Integration Dictionary'
    }
  }, [title])
}
