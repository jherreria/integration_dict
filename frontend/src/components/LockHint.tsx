export default function LockHint() {
  return (
    <span className="lock-hint" title="Only the integration team can change this field">
      <span aria-hidden="true">🔒</span>
      <span className="sr-only">Only the integration team can change this field</span>
    </span>
  )
}
