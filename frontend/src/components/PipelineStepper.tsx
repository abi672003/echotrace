import type { AnalysisStepOut, PipelineStepName, StepStatus } from '../api/types'

const STEP_ORDER: PipelineStepName[] = [
  'normalize',
  'embed',
  'cluster',
  'measure',
  'ai_score',
  'aggregate',
  'agent',
]

const STEP_LABELS: Record<PipelineStepName, string> = {
  normalize: 'Normalize',
  embed: 'Embed',
  cluster: 'Cluster',
  measure: 'Measure',
  ai_score: 'AI-style score',
  aggregate: 'Aggregate',
  agent: 'Agent review',
}

function statusColorClass(status: StepStatus): string {
  switch (status) {
    case 'done':
      return 'bg-organic'
    case 'running':
      return 'bg-thread'
    case 'failed':
      return 'bg-campaign'
    case 'skipped':
      return 'bg-unsure'
    default:
      return 'bg-rule'
  }
}

export function PipelineStepper({ steps }: { steps: AnalysisStepOut[] }) {
  const byName = new Map(steps.map((step) => [step.name, step]))
  const latest = [...steps].reverse().find((step) => step.status !== 'pending')
  const announcement = latest ? `${STEP_LABELS[latest.name]}: ${latest.status}` : ''

  return (
    <div>
      <ol className="flex flex-col gap-1.5">
        {STEP_ORDER.map((name, index) => {
          const step = byName.get(name)
          const status: StepStatus = step?.status ?? 'pending'
          return (
            <li key={name} className="flex items-center gap-2 text-sm">
              <span className="text-ink-soft" style={{ fontVariantNumeric: 'tabular-nums' }}>
                {index + 1}.
              </span>
              <span
                className={`h-2 w-2 rounded-chip ${statusColorClass(status)}`}
                aria-hidden="true"
              />
              <span className={status === 'failed' ? 'font-semibold text-campaign' : 'text-ink'}>
                {STEP_LABELS[name]}
              </span>
              <span className="text-xs text-ink-soft">{status}</span>
              {step?.detail && status === 'failed' && (
                <span className="text-xs text-campaign">— {step.detail}</span>
              )}
            </li>
          )
        })}
      </ol>
      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>
    </div>
  )
}
