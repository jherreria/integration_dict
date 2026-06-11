// Shallow diff between the original record and the edit draft, producing a
// partial PATCH payload (only changed fields — required for per-field RBAC
// and clean audit entries). Arrays are compared as order-insensitive sets;
// '' and null are treated as distinct only where the backend distinguishes
// them (nullable lookups), which the form values already encode.

function arraysEqual(a: unknown[], b: unknown[]): boolean {
  if (a.length !== b.length) return false
  const sa = [...a].map(String).sort()
  const sb = [...b].map(String).sort()
  return sa.every((v, i) => v === sb[i])
}

export function shallowDiff<T extends Record<string, unknown>>(
  original: T,
  draft: T,
): Partial<T> {
  const out: Partial<T> = {}
  for (const key of Object.keys(draft) as (keyof T)[]) {
    const before = original[key]
    const after = draft[key]
    if (Array.isArray(before) && Array.isArray(after)) {
      if (!arraysEqual(before, after)) out[key] = after
    } else if (before !== after) {
      out[key] = after
    }
  }
  return out
}
