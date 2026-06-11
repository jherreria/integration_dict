import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { getMe } from '../api/lookups'
import type { Me } from '../api/types'

interface UserContextValue {
  me: Me | null
  loading: boolean
  error: string | null
  isAdmin: boolean
  adminOnlyFields: Set<string>
  /** Can the current user edit this field on an existing integration? */
  canEditField: (field: string) => boolean
}

const UserContext = createContext<UserContextValue>({
  me: null,
  loading: true,
  error: null,
  isAdmin: false,
  adminOnlyFields: new Set(),
  canEditField: () => false,
})

export function UserProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const value = useMemo<UserContextValue>(() => {
    const adminOnlyFields = new Set(me?.admin_only_fields ?? [])
    const isAdmin = me?.is_admin ?? false
    return {
      me,
      loading,
      error,
      isAdmin,
      adminOnlyFields,
      canEditField: (field: string) => isAdmin || !adminOnlyFields.has(field),
    }
  }, [me, loading, error])

  return <UserContext.Provider value={value}>{children}</UserContext.Provider>
}

export const useUser = () => useContext(UserContext)
