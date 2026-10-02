import { Link } from 'react-router-dom'
import { useDockets } from '../api/hooks'
import { DocketForm } from '../components/DocketForm'
import { EmptyState } from '../components/EmptyState'
import { ErrorState } from '../components/ErrorState'
import { IngestProgress } from '../components/IngestProgress'
import { SampleList } from '../components/SampleList'

export function DocketsPage() {
  const { data: dockets, isLoading, isError } = useDockets()

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <section className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold">Dockets</h1>
        <DocketForm />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-ink-soft">Bundled samples</h2>
        <SampleList />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-ink-soft">Your dockets</h2>
        {isError && <ErrorState message="Could not load dockets. Check the backend connection." />}
        {isLoading && <p className="text-ink-soft">Loading dockets…</p>}
        {!isLoading && dockets && dockets.length === 0 && (
          <EmptyState message="No dockets yet. Add a docket ID or load a sample." />
        )}
        {dockets && dockets.length > 0 && (
          <ul className="flex flex-col gap-2">
            {dockets.map((docket) => (
              <li key={docket.id} className="rounded-sheet border border-rule bg-paper p-3 shadow-sheet">
                <Link to={`/dockets/${docket.id}`} className="font-semibold text-thread hover:underline">
                  {docket.id}
                </Link>
                <div className="mt-2">
                  <IngestProgress docket={docket} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
