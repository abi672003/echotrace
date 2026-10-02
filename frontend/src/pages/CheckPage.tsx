import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAnalysis, useCreateAnalysis, useDockets } from '../api/hooks'
import { ErrorState } from '../components/ErrorState'
import { VerdictTag } from '../components/VerdictTag'

const MIN_WORDS = 25

export function CheckPage() {
  const [docketId, setDocketId] = useState('')
  const [text, setText] = useState('')
  const [analysisId, setAnalysisId] = useState<string | null>(null)

  const { data: dockets } = useDockets()
  const createAnalysis = useCreateAnalysis()
  const { data: analysis } = useAnalysis(analysisId ?? undefined)

  const ingestedDockets = (dockets ?? []).filter((d) => d.ingested_count > 0)
  const wordCount = text.trim().split(/\s+/).filter(Boolean).length
  const canSubmit = Boolean(docketId) && wordCount >= MIN_WORDS && !createAnalysis.isPending

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return
    createAnalysis.mutate(
      { mode: 'text', docket_id: docketId, text },
      { onSuccess: (result) => setAnalysisId(result.analysis_id) },
    )
  }

  const cluster = analysis?.clusters[0]

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-4">
      <h1 className="text-xl font-semibold">Check a comment</h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Docket
          <select
            value={docketId}
            onChange={(event) => setDocketId(event.target.value)}
            className="rounded-control border border-rule bg-paper px-3 py-2"
          >
            <option value="">Choose an ingested docket…</option>
            {ingestedDockets.map((docket) => (
              <option key={docket.id} value={docket.id}>
                {docket.id}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Comment text
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={6}
            className="rounded-control border border-rule bg-paper px-3 py-2 font-serif"
          />
        </label>
        <p className="text-xs text-ink-soft">
          {wordCount} / {MIN_WORDS} words minimum
        </p>
        <button
          type="submit"
          disabled={!canSubmit}
          className="self-start rounded-control bg-thread px-4 py-2 text-sm font-semibold text-paper disabled:opacity-60"
        >
          {createAnalysis.isPending ? 'Checking…' : 'Check comment'}
        </button>
        {createAnalysis.isError && (
          <ErrorState message="Could not check this comment. An analysis may already be running." />
        )}
      </form>

      {analysis && (analysis.status === 'queued' || analysis.status === 'running') && (
        <p className="text-ink-soft">Checking…</p>
      )}

      {analysis && analysis.status === 'done' && (
        <div className="rounded-sheet border border-rule bg-paper p-4 shadow-sheet">
          {cluster ? (
            <div>
              <VerdictTag type={cluster.verdict_type ?? cluster.preliminary_type} />
              <p className="mt-2 text-sm text-ink">
                Aggregate AI-style signal: {cluster.metrics.ai_agg.toFixed(2)}
              </p>
              {analysisId && (
                <Link to={`/analyses/${analysisId}`} className="mt-2 inline-block text-thread hover:underline">
                  View family
                </Link>
              )}
            </div>
          ) : (
            <p className="text-ink">No family found.</p>
          )}
        </div>
      )}
    </div>
  )
}
