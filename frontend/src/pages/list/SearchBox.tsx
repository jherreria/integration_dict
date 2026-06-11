import Spinner from '../../components/Spinner'

interface SearchBoxProps {
  value: string
  onChange: (value: string) => void
  loading: boolean
  /** True when the AI search endpoint is configured (toggle is shown). */
  aiAvailable: boolean
  aiOn: boolean
  onToggleAi: () => void
}

export default function SearchBox({
  value,
  onChange,
  loading,
  aiAvailable,
  aiOn,
  onToggleAi,
}: SearchBoxProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ flex: '0 1 420px' }}>
        <input
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Search integrations…"
          aria-label="Search integrations"
        />
      </div>
      {aiAvailable && (
        <button
          type="button"
          className={`btn small${aiOn ? '' : ' secondary'}`}
          style={{ borderRadius: 999 }}
          aria-pressed={aiOn}
          onClick={onToggleAi}
          title={
            aiOn
              ? 'AI search is on — results are ranked by relevance'
              : 'AI search is off — using keyword search'
          }
        >
          AI
        </button>
      )}
      {loading && <Spinner label="Searching…" />}
    </div>
  )
}
