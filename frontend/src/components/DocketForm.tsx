import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCreateDocket } from '../api/hooks'

const DOCKET_ID_PATTERN = /^[A-Z0-9-]+$/

export function DocketForm() {
  const [docketId, setDocketId] = useState('')
  const [touched, setTouched] = useState(false)
  const navigate = useNavigate()
  const createDocket = useCreateDocket()

  const isValid = DOCKET_ID_PATTERN.test(docketId)

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    setTouched(true)
    if (!isValid) return
    createDocket.mutate(
      { docket_id: docketId },
      { onSuccess: (docket) => navigate(`/dockets/${docket.id}`) },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-start">
      <div className="flex-1">
        <label htmlFor="docket-id" className="sr-only">
          Docket ID
        </label>
        <input
          id="docket-id"
          value={docketId}
          onChange={(event) => setDocketId(event.target.value.toUpperCase())}
          placeholder="EPA-HQ-OAR-2021-0317"
          className="w-full rounded-control border border-rule bg-paper px-3 py-2 text-sm"
          aria-invalid={touched && !isValid}
          aria-describedby="docket-id-error"
        />
        {touched && !isValid && (
          <p id="docket-id-error" className="mt-1 text-xs text-campaign">
            Use only uppercase letters, numbers, and hyphens.
          </p>
        )}
      </div>
      <button
        type="submit"
        disabled={createDocket.isPending}
        className="rounded-control bg-thread px-4 py-2 text-sm font-semibold text-paper disabled:opacity-60"
      >
        {createDocket.isPending ? 'Fetching…' : 'Fetch comments'}
      </button>
    </form>
  )
}
