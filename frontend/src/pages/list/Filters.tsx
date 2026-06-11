import { useEffect, useId, useState } from 'react'
import { getSystems, getTags, getTypes } from '../../api/lookups'
import type { NamedOut, Status } from '../../api/types'
import { STATUS_LABELS } from '../../components/StatusBadge'

export const ALL_STATUSES = Object.keys(STATUS_LABELS) as Status[]

interface FiltersProps {
  statuses: Status[]
  type: string
  tag: string
  system: string
  onStatusesChange: (statuses: Status[]) => void
  onTypeChange: (value: string) => void
  onTagChange: (value: string) => void
  onSystemChange: (value: string) => void
  onClear: () => void
}

function LookupSelect({
  label,
  allLabel,
  value,
  options,
  onChange,
}: {
  label: string
  allLabel: string
  value: string
  options: NamedOut[]
  onChange: (value: string) => void
}) {
  const id = useId()
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ width: 'auto', minWidth: 140 }}
      >
        <option value="">{allLabel}</option>
        {options.map((opt) => (
          <option key={opt.id} value={opt.name}>
            {opt.name}
          </option>
        ))}
      </select>
    </span>
  )
}

export default function Filters({
  statuses,
  type,
  tag,
  system,
  onStatusesChange,
  onTypeChange,
  onTagChange,
  onSystemChange,
  onClear,
}: FiltersProps) {
  const [types, setTypes] = useState<NamedOut[]>([])
  const [tags, setTags] = useState<NamedOut[]>([])
  const [systems, setSystems] = useState<NamedOut[]>([])

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([getTypes(), getTags(), getSystems()]).then(([t, g, s]) => {
      if (cancelled) return
      if (t.status === 'fulfilled') setTypes(t.value)
      if (g.status === 'fulfilled') setTags(g.value)
      if (s.status === 'fulfilled') setSystems(s.value)
    })
    return () => {
      cancelled = true
    }
  }, [])

  function toggleStatus(status: Status) {
    onStatusesChange(
      statuses.includes(status)
        ? statuses.filter((s) => s !== status)
        : [...statuses, status],
    )
  }

  const anyActive = statuses.length > 0 || type !== '' || tag !== '' || system !== ''

  return (
    <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 16, marginTop: 12 }}>
      <fieldset
        style={{
          border: 'none',
          margin: 0,
          padding: 0,
          display: 'inline-flex',
          alignItems: 'center',
          gap: 10,
          flexWrap: 'wrap',
        }}
      >
        <legend className="sr-only">Filter by status</legend>
        {ALL_STATUSES.map((status) => (
          <label
            key={status}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontWeight: 400 }}
          >
            <input
              type="checkbox"
              checked={statuses.includes(status)}
              onChange={() => toggleStatus(status)}
            />
            {STATUS_LABELS[status]}
          </label>
        ))}
      </fieldset>
      <LookupSelect label="Type" allLabel="All types" value={type} options={types} onChange={onTypeChange} />
      <LookupSelect label="Tag" allLabel="All tags" value={tag} options={tags} onChange={onTagChange} />
      <LookupSelect label="System" allLabel="All systems" value={system} options={systems} onChange={onSystemChange} />
      {anyActive && (
        <button type="button" className="btn link" onClick={onClear}>
          Clear filters
        </button>
      )}
    </div>
  )
}
