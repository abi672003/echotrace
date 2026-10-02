import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useAnalysis, useCluster, useClusterGraph } from '../api/hooks'
import { CompareTray } from '../components/CompareTray'
import { ErrorState } from '../components/ErrorState'
import { EvidenceBoard } from '../components/EvidenceBoard'
import { FamilyList } from '../components/FamilyList'
import { PipelineStepper } from '../components/PipelineStepper'
import { VerdictDrawer } from '../components/VerdictDrawer'

export function AnalysisPage() {
  const { analysisId } = useParams<{ analysisId: string }>()
  const [selectedClusterId, setSelectedClusterId] = useState<number | null>(null)
  const [selectedDocId, setSelectedDocId] = useState<number | null>(null)
  const [compareIds, setCompareIds] = useState<[number, number] | null>(null)

  const { data: analysis, isError } = useAnalysis(analysisId)

  const activeClusterId = selectedClusterId ?? analysis?.clusters[0]?.id ?? undefined
  const { data: cluster } = useCluster(activeClusterId)
  const { data: graph } = useClusterGraph(activeClusterId)

  if (isError) {
    return <ErrorState message="Could not load this analysis." />
  }
  if (!analysis) {
    return <p className="text-ink-soft">Loading analysis…</p>
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-semibold">Analysis — {analysis.docket_id}</h1>
        <div className="mt-2">
          <PipelineStepper steps={analysis.steps} />
        </div>
        {analysis.summary && <p className="mt-2 text-sm text-ink">{analysis.summary}</p>}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr_360px]">
        <aside>
          <FamilyList
            clusters={analysis.clusters}
            selectedId={activeClusterId ?? null}
            onSelect={(id) => {
              setSelectedClusterId(id)
              setSelectedDocId(null)
              setCompareIds(null)
            }}
          />
        </aside>

        <section>
          {graph && cluster ? (
            <EvidenceBoard
              graph={graph}
              verdictType={cluster.verdict_type ?? cluster.preliminary_type}
              citedDocumentIds={cluster.cited_document_ids}
              selectedId={selectedDocId}
              onSelect={setSelectedDocId}
              onCompare={(a, b) => setCompareIds([a, b])}
            />
          ) : (
            <p className="text-ink-soft">Select a family to see its evidence board.</p>
          )}
        </section>

        <aside>
          {cluster && analysisId ? (
            <VerdictDrawer
              cluster={cluster}
              analysisId={analysisId}
              onCitationClick={setSelectedDocId}
            />
          ) : (
            <p className="text-ink-soft">No family selected.</p>
          )}
        </aside>
      </div>

      {compareIds && (
        <CompareTray
          docAId={compareIds[0]}
          docBId={compareIds[1]}
          onClose={() => setCompareIds(null)}
        />
      )}
    </div>
  )
}
