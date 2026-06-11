import type { Status } from '../api/types'

export const STATUS_LABELS: Record<Status, string> = {
  planning: 'Planning',
  dev: 'Dev',
  test: 'Test',
  qa: 'QA',
  prod: 'Prod',
  fixing: 'Fixing',
}

/** Single source of truth for status colors (table badges, DAG nodes, legend). */
export function statusColors(status: Status): { bg: string; fg: string } {
  return {
    bg: `var(--status-${status}-bg)`,
    fg: `var(--status-${status}-fg)`,
  }
}

export default function StatusBadge({ status }: { status: Status }) {
  const { bg, fg } = statusColors(status)
  return (
    <span className="status-badge" style={{ background: bg, color: fg }}>
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}
