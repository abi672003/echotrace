import type { ReactNode } from 'react'
import { useCompareDocuments, useDocument } from '../api/hooks'

function renderHighlighted(text: string, ranges: { start: number; end: number }[]): ReactNode[] {
  const sorted = [...ranges].sort((a, b) => a.start - b.start)
  const parts: ReactNode[] = []
  let cursor = 0
  sorted.forEach((range, index) => {
    if (range.start > cursor) {
      parts.push(text.slice(cursor, range.start))
    }
    parts.push(
      <mark key={index} style={{ backgroundColor: 'var(--marker)' }} className="rounded-sm">
        {text.slice(range.start, range.end)}
      </mark>,
    )
    cursor = Math.max(cursor, range.end)
  })
  if (cursor < text.length) {
    parts.push(text.slice(cursor))
  }
  return parts
}

interface CompareTrayProps {
  docAId: number
  docBId: number
  onClose: () => void
}

export function CompareTray({ docAId, docBId, onClose }: CompareTrayProps) {
  const { data: compare } = useCompareDocuments(docAId, docBId)
  const { data: docA } = useDocument(docAId)
  const { data: docB } = useDocument(docBId)

  return (
    <div className="rounded-sheet border border-rule bg-paper p-4 shadow-sheet">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold">Compare</h3>
        <button
          type="button"
          onClick={onClose}
          className="text-xs font-semibold text-ink-soft hover:text-ink"
        >
          Close
        </button>
      </div>
      {compare && (
        <p className="mb-3 text-xs text-ink-soft" style={{ fontVariantNumeric: 'tabular-nums' }}>
          Semantic similarity {compare.sem.toFixed(2)} · Lexical overlap {compare.lex.toFixed(2)}
        </p>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <p className="mb-1 text-xs font-semibold text-ink-soft">Comment A</p>
          {docA && compare ? (
            <p className="font-serif text-sm leading-[1.65] text-ink">
              {renderHighlighted(
                docA.text,
                compare.shared.map((s) => ({ start: s.a_start, end: s.a_end })),
              )}
            </p>
          ) : (
            <p className="text-ink-soft">Loading…</p>
          )}
        </div>
        <div>
          <p className="mb-1 text-xs font-semibold text-ink-soft">Comment B</p>
          {docB && compare ? (
            <p className="font-serif text-sm leading-[1.65] text-ink">
              {renderHighlighted(
                docB.text,
                compare.shared.map((s) => ({ start: s.b_start, end: s.b_end })),
              )}
            </p>
          ) : (
            <p className="text-ink-soft">Loading…</p>
          )}
        </div>
      </div>
    </div>
  )
}
