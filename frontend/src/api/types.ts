// TypeScript mirrors of the backend Pydantic schemas (backend/schemas.py).

export type Status = 'planning' | 'dev' | 'test' | 'qa' | 'prod' | 'fixing'
export type Level = 'low' | 'medium' | 'high'

export interface UserOut {
  id: string
  email: string
  display_name: string
  role: 'general' | 'integration'
}

export interface Me {
  user: UserOut
  is_admin: boolean
  admin_only_fields: string[]
}

export interface NamedOut {
  id: string
  name: string
}

export interface IntegrationRef {
  id: string
  name: string
  status: string
}

export interface IntegrationListItem {
  id: string
  name: string
  description: string
  status: Status
  type: string | null
  tags: string[]
  associated_projects: string[]
  sources: string[]
  targets: string[]
  created_at: string
  updated_at: string
  updated_by: string | null
}

export interface IntegrationDetail extends IntegrationListItem {
  documentation_url: string
  notes: string
  complexity: Level | null
  business_logic: Level | null
  design_approved: boolean
  design_approver: UserOut | null
  design_approval_date: string | null
  code_approved: boolean
  code_approver: UserOut | null
  code_approval_date: string | null
  credential_type: string | null
  account_used: string
  needed_roles: string
  upstream: IntegrationRef[]
  downstream: IntegrationRef[]
  integrated: IntegrationRef[]
  version: number
  created_by: string | null
  deleted_at: string | null
}

// Partial update payload. tags/sources/targets are NAME lists;
// upstream/downstream/integrated are integration-ID lists; approvers are
// app_user IDs. `version` is an optimistic-concurrency precondition.
export interface IntegrationUpdatePayload {
  name?: string
  description?: string
  status?: Status
  type?: string | null
  tags?: string[]
  sources?: string[]
  targets?: string[]
  upstream?: string[]
  downstream?: string[]
  integrated?: string[]
  associated_projects?: string[]
  documentation_url?: string
  notes?: string
  complexity?: Level | null
  business_logic?: Level | null
  design_approved?: boolean
  design_approver_id?: string | null
  design_approval_date?: string | null
  code_approved?: boolean
  code_approver_id?: string | null
  code_approval_date?: string | null
  credential_type?: string | null
  account_used?: string
  needed_roles?: string
  version?: number
}

export interface IntegrationCreatePayload extends IntegrationUpdatePayload {
  name: string
}

export type SearchMode = 'keyword' | 'ai'

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  search_mode_used: SearchMode | null
}

export interface AuditEntry {
  id: string
  integration_id: string
  integration_name: string
  action: 'created' | 'updated' | 'deleted' | 'restored' | 'commented'
  field: string | null
  old_value: string | null
  new_value: string | null
  change_group_id: string
  changed_by_email: string
  changed_by_name: string
  changed_at: string
}

export interface AuditPage {
  items: AuditEntry[]
  total: number
  page: number
  page_size: number
}

export interface Attachment {
  id: string
  filename: string
  content_type: string
  size_bytes: number
}

export interface Comment {
  id: string
  integration_id: string
  body: string
  author_email: string
  author_name: string
  created_at: string
  attachments: Attachment[]
}

export interface CommentPage {
  items: Comment[]
  total: number
  page: number
  page_size: number
}

export interface GraphNode {
  id: string
  name: string
  status: Status
  is_root: boolean
}

export interface GraphEdge {
  source: string
  target: string
  kind: 'flow' | 'integrated'
}

export interface GraphPayload {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface SearchStatus {
  endpoint_configured: boolean
  endpoint: string | null
  total: number
  embedded: number
  stale: number
}

export interface Enums {
  statuses: Status[]
  levels: Level[]
}

export interface ListParams {
  q?: string
  mode?: SearchMode
  status?: Status[]
  type?: string
  tag?: string
  system?: string
  sort?: string
  order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}
