import { useEffect, useId, useMemo, useRef, useState } from 'react'

export interface MSOption {
  value: string
  label: string
}

interface MultiSelectCreatableProps {
  values: string[]
  options: MSOption[]
  onChange: (values: string[]) => void
  /** Allow creating a new option from the typed text (value === label). */
  creatable?: boolean
  disabled?: boolean
  placeholder?: string
  inputId?: string
  /** Values that may not be selected (e.g. the integration itself). */
  excludeValues?: string[]
}

export default function MultiSelectCreatable({
  values,
  options,
  onChange,
  creatable = false,
  disabled = false,
  placeholder = 'Type to search…',
  inputId,
  excludeValues = [],
}: MultiSelectCreatableProps) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listId = useId()

  const labelFor = useMemo(() => {
    const map = new Map(options.map((o) => [o.value, o.label]))
    return (value: string) => map.get(value) ?? value
  }, [options])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const excluded = new Set([...values, ...excludeValues])
    return options
      .filter((o) => !excluded.has(o.value))
      .filter((o) => !q || o.label.toLowerCase().includes(q))
      .slice(0, 50)
  }, [options, values, excludeValues, query])

  const canCreate =
    creatable &&
    query.trim().length > 0 &&
    !options.some((o) => o.label.toLowerCase() === query.trim().toLowerCase()) &&
    !values.some((v) => v.toLowerCase() === query.trim().toLowerCase())

  const items: Array<MSOption | { create: true; label: string }> = useMemo(() => {
    const base: Array<MSOption | { create: true; label: string }> = [...filtered]
    if (canCreate) base.push({ create: true, label: query.trim() })
    return base
  }, [filtered, canCreate, query])

  useEffect(() => {
    setActiveIndex((i) => Math.min(i, Math.max(items.length - 1, 0)))
  }, [items.length])

  useEffect(() => {
    function onDocMouseDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    return () => document.removeEventListener('mousedown', onDocMouseDown)
  }, [])

  function select(item: MSOption | { create: true; label: string }) {
    const value = 'create' in item ? item.label : item.value
    onChange([...values, value])
    setQuery('')
    setOpen(false)
    inputRef.current?.focus()
  }

  function remove(value: string) {
    onChange(values.filter((v) => v !== value))
    inputRef.current?.focus()
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setActiveIndex((i) => Math.min(i + 1, items.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      if (open && items[activeIndex]) {
        e.preventDefault()
        select(items[activeIndex])
      } else if (canCreate) {
        e.preventDefault()
        select({ create: true, label: query.trim() })
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    } else if (e.key === 'Backspace' && query === '' && values.length > 0) {
      remove(values[values.length - 1])
    }
  }

  return (
    <div className={`msel ${disabled ? 'disabled' : ''}`} ref={rootRef}>
      <div
        className="msel-control"
        onClick={() => {
          if (!disabled) inputRef.current?.focus()
        }}
      >
        {values.map((v) => (
          <span className="msel-chip" key={v}>
            {labelFor(v)}
            {!disabled && (
              <button
                type="button"
                aria-label={`Remove ${labelFor(v)}`}
                onClick={() => remove(v)}
              >
                ×
              </button>
            )}
          </span>
        ))}
        <input
          id={inputId}
          ref={inputRef}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && items[activeIndex] ? `${listId}-${activeIndex}` : undefined}
          value={query}
          placeholder={values.length === 0 ? placeholder : ''}
          disabled={disabled}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
            setActiveIndex(0)
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
      </div>
      {open && !disabled && (
        <ul className="msel-list" role="listbox" id={listId} aria-multiselectable="true">
          {items.length === 0 && <li className="empty">No matches</li>}
          {items.map((item, idx) => {
            const isCreate = 'create' in item
            return (
              <li
                key={isCreate ? `__create__${item.label}` : item.value}
                id={`${listId}-${idx}`}
                role="option"
                aria-selected={false}
                className={`${idx === activeIndex ? 'active' : ''} ${isCreate ? 'create-option' : ''}`}
                onMouseEnter={() => setActiveIndex(idx)}
                onMouseDown={(e) => {
                  e.preventDefault()
                  select(item)
                }}
              >
                {isCreate ? `Create “${item.label}”` : item.label}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
