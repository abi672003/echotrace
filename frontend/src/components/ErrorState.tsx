export function ErrorState({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-sheet border border-campaign bg-paper p-4 text-campaign"
    >
      {message}
    </div>
  )
}
