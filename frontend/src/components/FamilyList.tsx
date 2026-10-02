import type { ClusterSummary } from '../api/types'
import { VerdictTag } from './VerdictTag'

interface FamilyListProps {
  clusters: ClusterSummary[]
  selectedId: number | null
  onSelect: (id: number) => void
}

export function FamilyList({ clusters, selectedId, onSelect }: FamilyListProps) {
  if (clusters.length === 0) {
    return <p className="text-ink-soft">No families found yet.</p>
  }

  return (
    <ul className="flex flex-col gap-1">
      {clusters.map((cluster) => (
        <li key={cluster.id}>
          <button
            type="button"
            onClick={() => onSelect(cluster.id)}
            aria-current={selectedId === cluster.id}
            className={`flex w-full flex-col gap-1 rounded-control border px-3 py-2 text-left ${
              selectedId === cluster.id
                ? 'border-thread bg-paper'
                : 'border-transparent hover:bg-paper'
            }`}
          >
            <span
              className="flex items-center justify-between"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              <span className="font-semibold">
                {cluster.size} · {cluster.campaign_score.toFixed(2)}
              </span>
              {cluster.review_status !== 'unreviewed' && (
                <span className="text-xs text-ink-soft">{cluster.review_status}</span>
              )}
            </span>
            <VerdictTag type={cluster.verdict_type ?? cluster.preliminary_type} />
          </button>
        </li>
      ))}
    </ul>
  )
}
