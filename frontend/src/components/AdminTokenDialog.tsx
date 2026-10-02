import { useState } from 'react'
import { useAdminToken } from '../context/AdminTokenContext'

export function AdminTokenDialog() {
  const { token, setToken } = useAdminToken()
  const [draft, setDraft] = useState(token)
  const [open, setOpen] = useState(false)

  return (
    <div className="text-sm">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="rounded-control border border-rule px-3 py-1 text-ink-soft hover:text-ink"
      >
        {token ? 'Admin token set' : 'Set admin token'}
      </button>
      {open && (
        <div className="mt-2 flex items-center gap-2">
          <input
            type="password"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="X-Admin-Token"
            className="rounded-control border border-rule px-2 py-1"
          />
          <button
            type="button"
            onClick={() => {
              setToken(draft)
              setOpen(false)
            }}
            className="rounded-control bg-thread px-3 py-1 text-paper"
          >
            Save
          </button>
        </div>
      )}
    </div>
  )
}
