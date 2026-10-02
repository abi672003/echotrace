import type { ClusterOut } from '../api/types'
import { verdictSentence } from '../lib/copy'
import { AgentTrace } from './AgentTrace'
import { CitationChip } from './CitationChip'
import { MetricTable } from './MetricTable'
import { ReviewBar } from './ReviewBar'
import { VerdictTag } from './VerdictTag'

interface VerdictDrawerProps {
  cluster: ClusterOut
  analysisId: string
  onCitationClick: (docId: number) => void
}

export function VerdictDrawer({ cluster, analysisId, onCitationClick }: VerdictDrawerProps) {
  const type = cluster.verdict_type ?? cluster.preliminary_type
  const sentence = verdictSentence(type, cluster.size, cluster.metrics.burst_24h)

  return (
    <div className="flex flex-col gap-4">
      <div>
        <VerdictTag type={type} />
        {cluster.confidence && (
          <p className="mt-1 text-xs text-ink-soft">Confidence: {cluster.confidence}</p>
        )}
        <p className="mt-2 text-sm font-semibold text-ink">{sentence}</p>
      </div>

      {cluster.rationale && (
        <div>
          <p className="text-sm text-ink">{cluster.rationale}</p>
          {cluster.cited_document_ids.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {cluster.cited_document_ids.map((id, index) => (
                <CitationChip key={id} number={index + 1} onClick={() => onCitationClick(id)} />
              ))}
            </div>
          )}
          {cluster.citations_corrected && (
            <p className="mt-1 text-xs text-ink-soft">Citations corrected.</p>
          )}
        </div>
      )}

      <MetricTable metrics={cluster.metrics} />

      <ReviewBar clusterId={cluster.id} />

      <AgentTrace analysisId={analysisId} clusterId={cluster.id} />
    </div>
  )
}
