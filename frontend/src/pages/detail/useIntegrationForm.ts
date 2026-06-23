// Edit-form state for the integration detail page: original vs draft values,
// dirty tracking via shallowDiff, and PATCH payload construction (changed
// fields only + optimistic-concurrency version).
import { useCallback, useEffect, useMemo, useState } from 'react'
import type {
  IntegrationDetail,
  IntegrationUpdatePayload,
  Level,
  Status,
} from '../../api/types'
import { shallowDiff } from '../../utils/diff'

/** Editable fields, keyed exactly like the backend PATCH payload. */
export interface FormValues {
  name: string
  description: string
  status: Status
  type: string | null
  tags: string[]
  sources: string[]
  targets: string[]
  upstream: string[]
  downstream: string[]
  integrated: string[]
  associated_projects: string[]
  documentation_url: string
  notes: string
  complexity: Level | null
  business_logic: Level | null
  design_approved: boolean
  design_approver_id: string | null
  design_approval_date: string | null
  code_approved: boolean
  code_approver_id: string | null
  code_approval_date: string | null
  credential_type: string | null
  account_used: string
  needed_roles: string
}

export function detailToFormValues(detail: IntegrationDetail): FormValues {
  return {
    name: detail.name,
    description: detail.description,
    status: detail.status,
    type: detail.type,
    tags: [...detail.tags],
    sources: [...detail.sources],
    targets: [...detail.targets],
    upstream: detail.upstream.map((r) => r.id),
    downstream: detail.downstream.map((r) => r.id),
    integrated: detail.integrated.map((r) => r.id),
    associated_projects: detail.associated_projects,
    documentation_url: detail.documentation_url,
    notes: detail.notes,
    complexity: detail.complexity,
    business_logic: detail.business_logic,
    design_approved: detail.design_approved,
    design_approver_id: detail.design_approver?.id ?? null,
    design_approval_date: detail.design_approval_date,
    code_approved: detail.code_approved,
    code_approver_id: detail.code_approver?.id ?? null,
    code_approval_date: detail.code_approval_date,
    credential_type: detail.credential_type,
    account_used: detail.account_used,
    needed_roles: detail.needed_roles,
  }
}

function diff(original: FormValues, draft: FormValues): Partial<FormValues> {
  return shallowDiff(
    original as unknown as Record<string, unknown>,
    draft as unknown as Record<string, unknown>,
  ) as Partial<FormValues>
}

export interface IntegrationForm {
  original: FormValues
  draft: FormValues
  set: <K extends keyof FormValues>(field: K, value: FormValues[K]) => void
  reset: () => void
  dirty: boolean
  changedCount: number
  buildPatch: () => IntegrationUpdatePayload
  fieldErrors: Record<string, string>
  setFieldErrors: React.Dispatch<React.SetStateAction<Record<string, string>>>
}

export function useIntegrationForm(detail: IntegrationDetail): IntegrationForm {
  const [original, setOriginal] = useState<FormValues>(() => detailToFormValues(detail))
  const [draft, setDraft] = useState<FormValues>(original)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  // Re-baseline whenever the server record changes (fresh load or after save).
  useEffect(() => {
    const values = detailToFormValues(detail)
    setOriginal(values)
    setDraft(values)
    setFieldErrors({})
  }, [detail])

  const set = useCallback(<K extends keyof FormValues>(field: K, value: FormValues[K]) => {
    setDraft((prev) => ({ ...prev, [field]: value }))
  }, [])

  const reset = useCallback(() => {
    setDraft(original)
    setFieldErrors({})
  }, [original])

  const changedCount = useMemo(
    () => Object.keys(diff(original, draft)).length,
    [original, draft],
  )

  const buildPatch = useCallback(
    (): IntegrationUpdatePayload => ({
      ...diff(original, draft),
      version: detail.version,
    }),
    [original, draft, detail.version],
  )

  return {
    original,
    draft,
    set,
    reset,
    dirty: changedCount > 0,
    changedCount,
    buildPatch,
    fieldErrors,
    setFieldErrors,
  }
}
