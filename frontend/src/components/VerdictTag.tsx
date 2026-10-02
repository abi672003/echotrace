import type { ClusterType } from '../api/types'

const LABELS: Record<ClusterType, string> = {
  coordinated_paraphrase_campaign: 'Campaign',
  form_letter: 'Form letter',
  organic_agreement: 'Organic',
  insufficient_evidence: 'Insufficient evidence',
}

const COLOR_CLASS: Record<ClusterType, string> = {
  coordinated_paraphrase_campaign: 'bg-campaign',
  form_letter: 'bg-form',
  organic_agreement: 'bg-organic',
  insufficient_evidence: 'bg-unsure',
}

export function VerdictTag({ type }: { type: ClusterType }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span className={`h-2 w-2 rounded-chip ${COLOR_CLASS[type]}`} aria-hidden="true" />
      {LABELS[type]}
    </span>
  )
}
