import { Link } from 'react-router-dom'
import type { IntegrationListItem } from '../../api/types'
import StatusBadge from '../../components/StatusBadge'
import { formatDate, formatDateTime, truncate } from '../../utils/format'

export type SortKey = 'name' | 'status' | 'created_at' | 'updated_at'

const COLUMNS: { label: string; sortKey?: SortKey }[] = [
  { label: 'Name', sortKey: 'name' },
  { label: 'Description' },
  { label: 'Sources' },
  { label: 'Targets' },
  { label: 'Lifecycle', sortKey: 'status' },
  { label: 'Tags' },
  { label: 'Created', sortKey: 'created_at' },
  { label: 'Updated', sortKey: 'updated_at' },
]

interface IntegrationsTableProps {
  items: IntegrationListItem[]
  sort: string
  order: 'asc' | 'desc'
  /** True while AI-ranked results are shown (header sorting is disabled). */
  sortDisabled: boolean
  onSort: (key: SortKey) => void
}

export default function IntegrationsTable({
  items,
  sort,
  order,
  sortDisabled,
  onSort,
}: IntegrationsTableProps) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          {COLUMNS.map((col) => {
            const sorted = col.sortKey !== undefined && sort === col.sortKey
            return (
              <th
                key={col.label}
                scope="col"
                aria-sort={sorted ? (order === 'asc' ? 'ascending' : 'descending') : undefined}
              >
                {col.sortKey ? (
                  <button
                    type="button"
                    onClick={() => onSort(col.sortKey!)}
                    disabled={sortDisabled}
                    title={
                      sortDisabled
                        ? 'Ranked by relevance while AI search is active'
                        : `Sort by ${col.label}`
                    }
                  >
                    {col.label}
                    {sorted && <span aria-hidden="true">{order === 'asc' ? '▲' : '▼'}</span>}
                  </button>
                ) : (
                  col.label
                )}
              </th>
            )
          })}
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.id}>
            <td>
              <Link to={`/integrations/${item.id}`}>{item.name}</Link>
            </td>
            <td>{truncate(item.description, 110)}</td>
            <td>
              {item.sources.map((s) => (
                <span key={s} className="chip system">
                  {s}
                </span>
              ))}
            </td>
            <td>
              {item.targets.map((t) => (
                <span key={t} className="chip system">
                  {t}
                </span>
              ))}
            </td>
            <td>
              <StatusBadge status={item.status} />
            </td>
            <td>
              {item.tags.map((t) => (
                <span key={t} className="chip">
                  {t}
                </span>
              ))}
            </td>
            <td>
              <span title={formatDateTime(item.created_at)}>{formatDate(item.created_at)}</span>
            </td>
            <td>
              <span title={item.updated_by ? `Updated by ${item.updated_by}` : undefined}>
                {formatDateTime(item.updated_at)}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
