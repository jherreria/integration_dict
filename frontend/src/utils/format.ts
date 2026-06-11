const dateTimeFmt = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})

const dateFmt = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
})

/** Backend datetimes are UTC; SQLite-sourced ones may lack a zone suffix. */
function parseUtc(value: string): Date {
  const hasZone = /Z$|[+-]\d{2}:?\d{2}$/.test(value)
  return new Date(hasZone ? value : `${value}Z`)
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = parseUtc(value)
  return Number.isNaN(d.getTime()) ? value : dateTimeFmt.format(d)
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  // Plain dates (YYYY-MM-DD) must not be shifted by the local timezone.
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (m) return dateFmt.format(new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])))
  const d = parseUtc(value)
  return Number.isNaN(d.getTime()) ? value : dateFmt.format(d)
}

export function truncate(text: string, max = 120): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}
