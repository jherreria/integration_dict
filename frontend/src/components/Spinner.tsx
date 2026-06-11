export default function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <span role="status">
      <span className="spinner" aria-hidden="true" /> <span className="sr-only">{label}</span>
    </span>
  )
}
