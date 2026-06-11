export default function EmptyState({
  title,
  children,
}: {
  title: string
  children?: React.ReactNode
}) {
  return (
    <div className="empty-state">
      <p>
        <strong>{title}</strong>
      </p>
      {children}
    </div>
  )
}
