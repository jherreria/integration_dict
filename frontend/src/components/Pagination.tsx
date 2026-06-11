interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
}

export default function Pagination({ page, pageSize, total, onPageChange }: PaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  if (pageCount <= 1) return null
  return (
    <nav className="pagination" aria-label="Pagination">
      <span className="muted">
        Page {page} of {pageCount} ({total} total)
      </span>
      <button
        type="button"
        className="btn secondary small"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        ← Prev
      </button>
      <button
        type="button"
        className="btn secondary small"
        disabled={page >= pageCount}
        onClick={() => onPageChange(page + 1)}
      >
        Next →
      </button>
    </nav>
  )
}
