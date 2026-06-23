import { get, post } from './client'
import type { Enums, Me, NamedOut, SearchStatus, UserOut } from './types'

export const getMe = () => get<Me>('/me')

export const getTags = () => get<NamedOut[]>('/lookups/tags')
export const getSystems = () => get<NamedOut[]>('/lookups/systems')
export const getTypes = () => get<NamedOut[]>('/lookups/types')
export const getCredentialTypes = () => get<NamedOut[]>('/lookups/credential-types')
export const getProjects = () => get<NamedOut[]>('/lookups/projects')
export const getEnums = () => get<Enums>('/lookups/enums')

// role=integration returns admins (the approver candidate list).
export const getUsers = (role?: 'general' | 'integration') =>
  get<UserOut[]>(`/lookups/users${role ? `?role=${role}` : ''}`)

let searchStatusPromise: Promise<SearchStatus> | null = null
export function getSearchStatus(force = false): Promise<SearchStatus> {
  if (!searchStatusPromise || force) {
    searchStatusPromise = get<SearchStatus>('/search/status')
  }
  return searchStatusPromise
}

export const reindexSearch = () => post<{ indexed: number; failed: number }>('/search/reindex')
