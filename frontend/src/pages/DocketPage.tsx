import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAnalyses, useCreateAnalysis, useDocket, useDocketDocuments } from '../api/hooks'
import { CommentSheet } from '../components/CommentSheet'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { IngestProgress } from '../components/IngestProgress'

export function DocketPage() {
  const { docketId } = useParams<{ docketId: string }>()
  const [search, setSearch] = useState('')
  const navigate = useNavigate()

  const { data: docket, isError: docketError } = useDocket(docketId)
  const { data: documents } = useDocketDocuments(docketId, {
    q: search || undefined,
    limit: 20,
  })
  const { data: analyses } = useAnalyses(docketId)
  const createAnalysis = useCreateAnalysis()

  if (docketError) {
    return <ErrorState message={`Could not load docket ${docketId}.`} />
  }
  if (!docket) {
    return <p className="text-ink-soft">Loading docket…</p>
  }

  const canAnalyse = docket.ingested_count > 0 && !createAnalysis.isPending

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <section>
        <h1 className="text-xl font-semibold">{docket.id}</h1>
        <div className="mt-2 max-w-sm">
          <IngestProgress docket={docket} />
        </div>
        <button
          type="button"
          disabled={!canAnalyse}
          onClick={() =>
            createAnalysis.mutate(
              { mode: 'docket', docket_id: docket.id },
              { onSuccess: (result) => navigate(`/analyses/${result.analysis_id}`) },
            )
          }
          className="mt-3 rounded-control bg-thread px-4 py-2 text-sm font-semibold text-paper disabled:opacity-60"
        >
          {createAnalysis.isPending ? 'Starting…' : 'Analyse docket'}
        </button>
        {createAnalysis.isError && (
          <div className="mt-2">
            <ErrorState message="Could not start analysis. An analysis may already be running." />
          </div>
        )}
      </section>

      <section>
        <h2 className="text-sm font-semibold text-ink-soft">Previous analyses</h2>
        {!analyses || analyses.length === 0 ? (
          <p className="mt-1 text-ink-soft">No analyses yet.</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-1">
            {analyses.map((analysis) => (
              <li key={analysis.id}>
                <Link
                  to={`/analyses/${analysis.id}`}
                  className="text-thread hover:underline"
                >
                  {new Date(analysis.created_at).toLocaleString()} — {analysis.status}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="text-sm font-semibold text-ink-soft">Comments</h2>
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search comment text…"
          className="mt-2 w-full rounded-control border border-rule bg-paper px-3 py-2 text-sm"
        />
        <div className="mt-3 flex flex-col gap-2">
          {documents && documents.items.length === 0 && (
            <EmptyState message="No comments match your search." />
          )}
          {documents?.items.map((doc) => (
            <CommentSheet
              key={doc.id}
              text={doc.text}
              submitterLabel={doc.submitter_label}
              submitterHash={doc.submitter_hash}
              postedAt={doc.posted_at}
              lines={3}
            />
          ))}
        </div>
      </section>
    </div>
  )
}
