import { useNavigate } from 'react-router-dom'
import { useLoadSample, useSamples } from '../api/hooks'

export function SampleList() {
  const { data: samples, isLoading } = useSamples()
  const loadSample = useLoadSample()
  const navigate = useNavigate()

  if (isLoading) {
    return <p className="text-ink-soft">Checking for bundled samples…</p>
  }

  if (!samples || samples.length === 0) {
    return null
  }

  return (
    <ul className="flex flex-col gap-2">
      {samples.map((sample) => (
        <li
          key={sample.name}
          className="flex items-center justify-between rounded-sheet border border-rule bg-paper p-3"
        >
          <div>
            <p className="font-semibold">{sample.docket_id}</p>
            <p className="text-xs text-ink-soft">{sample.count} comments bundled</p>
          </div>
          <button
            type="button"
            onClick={() =>
              loadSample.mutate(sample.name, {
                onSuccess: (docket) => navigate(`/dockets/${docket.id}`),
              })
            }
            disabled={loadSample.isPending}
            className="rounded-control border border-rule px-3 py-1 text-sm font-semibold text-ink hover:bg-desk disabled:opacity-60"
          >
            Load sample
          </button>
        </li>
      ))}
    </ul>
  )
}
