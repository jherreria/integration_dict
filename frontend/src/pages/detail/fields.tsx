// Field registry driving the detail page: which fields exist, what section
// they live in, what label they carry, and which input kind (and option
// source) renders them in edit mode.
import type { MSOption } from '../../components/MultiSelectCreatable'
import type { Level, Status, UserOut } from '../../api/types'
import type { FormValues } from './useIntegrationForm'

export type SectionKey =
  | 'overview'
  | 'systems'
  | 'relationships'
  | 'governance'
  | 'security'
  | 'notes'

export type FieldKind =
  | 'text'
  | 'textarea'
  | 'url'
  | 'status'
  | 'level'
  | 'lookup-type'
  | 'lookup-credential'
  | 'tags'
  | 'systems-multi'
  | 'integrations-multi'
  | 'boolean-approval'
  | 'user-select'
  | 'date'

/** Where each kind's edit-mode options come from (lookups API et al.). */
export type OptionSource =
  | 'tags'
  | 'systems'
  | 'types'
  | 'credential-types'
  | 'integrations'
  | 'users'
  | 'statuses'
  | 'levels'

export interface FieldDef {
  key: keyof FormValues
  label: string
  section: SectionKey
  kind: FieldKind
  /** Hint for which option list feeds this field in edit mode. */
  optionSource?: OptionSource
}

export const SECTIONS: Array<{ key: SectionKey; title: string }> = [
  { key: 'overview', title: 'Overview' },
  { key: 'systems', title: 'Systems & Data Flow' },
  { key: 'relationships', title: 'Relationships' },
  { key: 'governance', title: 'Governance & Approvals' },
  { key: 'security', title: 'Security & Access' },
  { key: 'notes', title: 'Notes' },
]

export const FIELDS: FieldDef[] = [
  // Overview
  { key: 'name', label: 'Name', section: 'overview', kind: 'text' },
  { key: 'description', label: 'Description', section: 'overview', kind: 'textarea' },
  { key: 'status', label: 'Status', section: 'overview', kind: 'status', optionSource: 'statuses' },
  { key: 'type', label: 'Type', section: 'overview', kind: 'lookup-type', optionSource: 'types' },
  { key: 'tags', label: 'Tags', section: 'overview', kind: 'tags', optionSource: 'tags' },
  { key: 'associated_projects', label: 'Associated projects', section: 'overview', kind: 'text' },
  { key: 'documentation_url', label: 'Documentation URL', section: 'overview', kind: 'url' },
  // Systems & Data Flow
  { key: 'sources', label: 'Source systems', section: 'systems', kind: 'systems-multi', optionSource: 'systems' },
  { key: 'targets', label: 'Target systems', section: 'systems', kind: 'systems-multi', optionSource: 'systems' },
  // Relationships
  { key: 'upstream', label: 'Upstream integrations', section: 'relationships', kind: 'integrations-multi', optionSource: 'integrations' },
  { key: 'downstream', label: 'Downstream integrations', section: 'relationships', kind: 'integrations-multi', optionSource: 'integrations' },
  { key: 'integrated', label: 'Integrated with', section: 'relationships', kind: 'integrations-multi', optionSource: 'integrations' },
  // Governance & Approvals
  { key: 'complexity', label: 'Complexity', section: 'governance', kind: 'level', optionSource: 'levels' },
  { key: 'business_logic', label: 'Business logic', section: 'governance', kind: 'level', optionSource: 'levels' },
  { key: 'design_approved', label: 'Design approved', section: 'governance', kind: 'boolean-approval' },
  { key: 'design_approver_id', label: 'Design approver', section: 'governance', kind: 'user-select', optionSource: 'users' },
  { key: 'design_approval_date', label: 'Design approval date', section: 'governance', kind: 'date' },
  { key: 'code_approved', label: 'Code approved', section: 'governance', kind: 'boolean-approval' },
  { key: 'code_approver_id', label: 'Code approver', section: 'governance', kind: 'user-select', optionSource: 'users' },
  { key: 'code_approval_date', label: 'Code approval date', section: 'governance', kind: 'date' },
  // Security & Access
  { key: 'credential_type', label: 'Credential type', section: 'security', kind: 'lookup-credential', optionSource: 'credential-types' },
  { key: 'account_used', label: 'Account used', section: 'security', kind: 'text' },
  { key: 'needed_roles', label: 'Needed roles', section: 'security', kind: 'text' },
  // Notes
  { key: 'notes', label: 'Notes', section: 'notes', kind: 'textarea' },
]

export const fieldsForSection = (section: SectionKey): FieldDef[] =>
  FIELDS.filter((f) => f.section === section)

/**
 * Human labels for audit-entry field names. The audit trail uses snapshot
 * keys, which match FormValues keys except for the approvers
 * (design_approver / code_approver, stored as emails).
 */
const AUDIT_LABELS: Record<string, string> = {
  ...Object.fromEntries(FIELDS.map((f) => [f.key, f.label])),
  design_approver: 'Design approver',
  code_approver: 'Code approver',
}

export const auditFieldLabel = (field: string): string => AUDIT_LABELS[field] ?? field

/** Option lists loaded for edit mode, shaped for the inputs that use them. */
export interface EditOptions {
  tags: MSOption[]
  systems: MSOption[]
  typeNames: string[]
  credentialTypeNames: string[]
  integrations: MSOption[]
  users: UserOut[]
  statuses: Status[]
  levels: Level[]
}
