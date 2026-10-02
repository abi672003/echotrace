export function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-sheet border border-dashed border-rule bg-paper p-6 text-center text-ink-soft">
      {message}
    </div>
  )
}
