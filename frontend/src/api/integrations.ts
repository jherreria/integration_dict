import { API_BASE, del, get, patch, post, postForm } from './client'
import type {
  AuditPage,
  Comment,
  CommentPage,
  GraphPayload,
  IntegrationCreatePayload,
  IntegrationDetail,
  IntegrationListItem,
  IntegrationUpdatePayload,
  ListParams,
  Page,
} from './types'

export function listIntegrations(params: ListParams, signal?: AbortSignal): Promise<Page<IntegrationListItem>> {
  const qs = new URLSearchParams()
  if (params.q) qs.set('q', params.q)
  if (params.mode) qs.set('mode', params.mode)
  for (const s of params.status ?? []) qs.append('status', s)
  if (params.type) qs.set('type', params.type)
  if (params.tag) qs.set('tag', params.tag)
  if (params.system) qs.set('system', params.system)
  if (params.sort) qs.set('sort', params.sort)
  if (params.order) qs.set('order', params.order)
  if (params.page) qs.set('page', String(params.page))
  if (params.page_size) qs.set('page_size', String(params.page_size))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return get(`/integrations${suffix}`, signal)
}

export const getIntegration = (id: string, signal?: AbortSignal) =>
  get<IntegrationDetail>(`/integrations/${id}`, signal)

export const createIntegration = (payload: IntegrationCreatePayload) =>
  post<IntegrationDetail>('/integrations', payload)

export const updateIntegration = (id: string, payload: IntegrationUpdatePayload) =>
  patch<IntegrationDetail>(`/integrations/${id}`, payload)

export const deleteIntegration = (id: string) => del<void>(`/integrations/${id}`)

export const getIntegrationAudit = (id: string, page = 1, pageSize = 25) =>
  get<AuditPage>(`/integrations/${id}/audit?page=${page}&page_size=${pageSize}`)

export const getIntegrationGraph = (id: string, depth: number | 'all', signal?: AbortSignal) =>
  get<GraphPayload>(`/integrations/${id}/graph${depth === 'all' ? '' : `?depth=${depth}`}`, signal)

export const getGlobalGraph = (signal?: AbortSignal) => get<GraphPayload>('/graph', signal)

export const getComments = (id: string, page = 1, pageSize = 25) =>
  get<CommentPage>(`/integrations/${id}/comments?page=${page}&page_size=${pageSize}`)

export function addComment(id: string, body: string, files: File[] = []): Promise<Comment> {
  const form = new FormData()
  form.append('body', body)
  for (const file of files) form.append('files', file)
  return postForm<Comment>(`/integrations/${id}/comments`, form)
}

export const attachmentUrl = (integrationId: string, commentId: string, attachmentId: string) =>
  `${API_BASE}/integrations/${integrationId}/comments/${commentId}/attachments/${attachmentId}`
