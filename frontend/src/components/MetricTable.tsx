import type { FullClusterMetrics } from '../api/types'

const METRIC_INFO: { key: keyof FullClusterMetrics; label: string; formula: string }[] = [
  { key: 'reword_index', label: 'Reword index', formula: 'mean_sem × (1 − mean_lex)' },
  { key: 'burst_24h', label: '24-hour burst share', formula: 'max members in any 24h window ÷ size' },
  { key: 'name_diversity', label: 'Name diversity', formula: 'distinct submitter hashes ÷ size' },
  {
    key: 'ai_agg',
    label: 'AI-style signal (unverified)',
    formula: 'similarity-weighted AI-style score across sampled members',
  },
  { key: 'mean_sem', label: 'Mean similarity', formula: 'mean cosine similarity to the representative comment' },
  {
    key: 'mean_lex',
    label: 'Mean lexical overlap',
    formula: 'mean Jaccard of word 3-grams to the representative comment',
  },
  { key: 'exact_dup_share', label: 'Exact duplicate share', formula: 'share of members with identical text' },
  { key: 'anon_share', label: 'Anonymous share', formula: 'share with no submitter name given' },
]

export function MetricTable({ metrics }: { metrics: FullClusterMetrics }) {
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Family metrics, with their formulas</caption>
      <tbody>
        {METRIC_INFO.map(({ key, label, formula }) => (
          <tr key={key} className="border-t border-rule">
            <th scope="row" className="group relative py-1.5 text-left font-normal text-ink-soft">
              <button type="button" className="underline decoration-dotted underline-offset-2">
                {label}
              </button>
              <span
                role="tooltip"
                className="pointer-events-none absolute left-0 top-full z-10 mt-1 hidden whitespace-nowrap rounded-control bg-ink px-2 py-1 text-xs text-paper group-hover:block group-focus-within:block"
              >
                {formula}
              </span>
            </th>
            <td
              className="py-1.5 text-right text-ink"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {metrics[key].toFixed(2)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
