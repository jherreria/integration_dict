// Compact legend for the DAG: status swatches plus the two edge kinds.

import type { Status } from '../../api/types'
import { STATUS_LABELS, statusColors } from '../../components/StatusBadge'

const STATUSES: Status[] = ['planning', 'dev', 'test', 'qa', 'prod', 'fixing']

export default function DagLegend() {
  return (
    <div className="card" style={{ padding: '10px 12px', fontSize: 12, lineHeight: 1.5 }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>Legend</div>
      <ul
        style={{
          listStyle: 'none',
          margin: 0,
          padding: 0,
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '2px 12px',
        }}
      >
        {STATUSES.map((status) => {
          const { bg, fg } = statusColors(status)
          return (
            <li key={status} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span
                aria-hidden="true"
                style={{
                  display: 'inline-block',
                  width: 12,
                  height: 12,
                  borderRadius: 3,
                  background: bg,
                  border: `2px solid ${fg}`,
                }}
              />
              {STATUS_LABELS[status]}
            </li>
          )
        })}
      </ul>
      <div
        style={{
          marginTop: 8,
          paddingTop: 8,
          borderTop: '1px solid var(--color-border)',
          display: 'grid',
          gap: 2,
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <svg width="30" height="10" aria-hidden="true">
            <line x1="0" y1="5" x2="23" y2="5" stroke="var(--ts-primary)" strokeWidth="2" />
            <polygon points="23,1 30,5 23,9" fill="var(--ts-primary)" />
          </svg>
          data flow
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <svg width="30" height="10" aria-hidden="true">
            <line x1="0" y1="5" x2="30" y2="5" stroke="#8a9aa4" strokeWidth="2" strokeDasharray="6 4" />
          </svg>
          integrated
        </span>
      </div>
    </div>
  )
}
