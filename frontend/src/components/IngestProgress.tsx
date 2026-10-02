import type { DocketOut } from '../api/types'

export function IngestProgress({ docket }: { docket: DocketOut }) {
  const total = docket.remote_comment_count ?? undefined
  const fetched = docket.ingested_count + docket.skipped_count
  const pct = total && total > 0 ? Math.min(100, Math.round((fetched / total) * 100)) : 0

  return (
    <div className="flex flex-col gap-1">
      <div className="h-2 w-full overflow-hidden rounded-chip bg-desk">
        <div
          className="h-full rounded-chip bg-thread transition-[width]"
          style={{ width: `${docket.ingest_status === 'done' ? 100 : pct}%` }}
        />
      </div>
      <p className="text-xs text-ink-soft" style={{ fontVariantNumeric: 'tabular-nums' }}>
        {docket.ingested_count}
        {total !== undefined ? ` of ${total}` : ''} fetched
        {docket.skipped_count > 0 ? `, ${docket.skipped_count} skipped` : ''}
      </p>
      {docket.ingest_status === 'partial' && (
        <p className="text-xs text-ink-soft">
          Paused at {fetched}
          {total !== undefined ? ` of ${total}` : ''}. Fetching resumes automatically.
        </p>
      )}
      {docket.ingest_status === 'failed' && docket.ingest_error && (
        <p className="text-xs text-campaign">{docket.ingest_error}</p>
      )}
    </div>
  )
}
