export function CitationChip({ number, onClick }: { number: number; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Jump to cited comment ${number}`}
      className="inline-flex h-5 w-5 items-center justify-center rounded-chip border border-thread text-xs font-semibold text-thread hover:bg-thread hover:text-paper"
    >
      {number}
    </button>
  )
}
