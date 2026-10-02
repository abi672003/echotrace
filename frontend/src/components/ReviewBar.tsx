import { useState } from 'react'
import { useSubmitReview } from '../api/hooks'
import type { ReviewDecision } from '../api/types'

export function ReviewBar({ clusterId }: { clusterId: number }) {
  const [note, setNote] = useState('')
  const [toast, setToast] = useState<string | null>(null)
  const submitReview = useSubmitReview(clusterId)

  const submit = (decision: ReviewDecision, verb: string) => {
    submitReview.mutate(
      { decision, note: note || undefined },
      {
        onSuccess: () => {
          setToast(verb)
          window.setTimeout(() => setToast(null), 3000)
        },
      },
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor="review-note" className="text-xs font-semibold text-ink-soft">
        Note (optional)
      </label>
      <textarea
        id="review-note"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        rows={2}
        className="rounded-control border border-rule bg-paper px-2 py-1 text-sm"
      />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => submit('confirmed', 'Confirmed')}
          disabled={submitReview.isPending}
          className="rounded-control bg-organic px-3 py-1.5 text-sm font-semibold text-paper disabled:opacity-60"
        >
          Confirm campaign
        </button>
        <button
          type="button"
          onClick={() => submit('rejected', 'Rejected')}
          disabled={submitReview.isPending}
          className="rounded-control border border-rule px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-60"
        >
          Reject
        </button>
        <button
          type="button"
          onClick={() => submit('unsure', 'Marked unsure')}
          disabled={submitReview.isPending}
          className="rounded-control border border-rule px-3 py-1.5 text-sm font-semibold text-ink disabled:opacity-60"
        >
          Mark unsure
        </button>
      </div>
      {toast && (
        <div role="status" aria-live="polite" className="text-sm font-semibold text-organic">
          {toast}
        </div>
      )}
    </div>
  )
}
