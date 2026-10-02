import { useState } from 'react'
import { useAnalysisTrace } from '../api/hooks'

export function AgentTrace({ analysisId, clusterId }: { analysisId: string; clusterId: number }) {
  const [open, setOpen] = useState(false)
  const { data: trace } = useAnalysisTrace(open ? analysisId : undefined, clusterId)

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="text-sm font-semibold text-thread"
      >
        {open ? 'Hide agent trace ▾' : 'Show agent trace ▸'}
      </button>
      {open && (
        <ol className="mt-2 flex flex-col gap-2 text-xs">
          {!trace && <li className="text-ink-soft">Loading trace…</li>}
          {trace?.map((step) => (
            <li key={step.step_no} className="rounded-control border border-rule bg-paper p-2">
              <p className="font-semibold text-ink">
                Step {step.step_no} · {step.action}
              </p>
              <p className="mt-1 break-words text-ink-soft">
                {JSON.stringify(step.observation).slice(0, 240)}
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
