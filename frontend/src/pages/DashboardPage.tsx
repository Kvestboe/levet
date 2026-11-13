import { Link } from 'react-router'
import type { Dashboard } from '../api.ts'
import { StatTile, WeaknessMeter } from '../components/progress.tsx'
import { ErrorMessage, Loading, PageTitle } from '../components/ui.tsx'
import { daysUntil, formatDate } from '../format.ts'
import { percent, weaknessLevel } from '../progress.ts'
import { useDashboard } from '../queries.ts'

export function DashboardPage() {
  const dashboard = useDashboard()
  return (
    <>
      <PageTitle>Dashboard</PageTitle>
      {dashboard.isPending ? (
        <Loading />
      ) : dashboard.isError ? (
        <ErrorMessage error={dashboard.error} />
      ) : (
        <Overview dashboard={dashboard.data} />
      )}
    </>
  )
}

function Overview({ dashboard }: { dashboard: Dashboard }) {
  if (dashboard.task_count === 0) return <GettingStarted hasSubjects={dashboard.subjects.length > 0} />

  const { due_count, streak_days, attempts_today, attempted_count, task_count } = dashboard
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile
          label="Due again"
          value={due_count}
          detail={due_count === 0 ? 'No failed tasks are waiting' : 'Failed tasks ready for another try'}
        />
        <StatTile
          label="Day streak"
          value={streak_days}
          detail={
            attempts_today > 0
              ? `${attempts_today} ${attempts_today === 1 ? 'attempt' : 'attempts'} today`
              : streak_days > 0
                ? 'Practise today to keep it going'
                : 'Starts with your first attempt'
          }
        />
        <StatTile
          label="Tasks attempted"
          value={attempted_count}
          detail={`of ${task_count} in approved exams`}
        />
      </div>

      <Link
        to="/practice"
        className="flex min-h-14 items-center justify-center rounded-xl bg-indigo-600 px-4 text-base font-medium text-white hover:bg-indigo-500"
      >
        Practise now
      </Link>

      <section aria-labelledby="exams-heading" className="space-y-2">
        <h2 id="exams-heading" className="text-base font-semibold">
          Exams
        </h2>
        <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
          {dashboard.subjects.map((subject) => (
            <li key={subject.code} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="font-mono text-sm font-semibold text-indigo-700">{subject.code}</p>
                <p className="text-sm break-words text-slate-600">{subject.name}</p>
              </div>
              <Countdown examDate={subject.exam_date} />
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="topics-heading" className="space-y-2">
        <h2 id="topics-heading" className="text-base font-semibold">
          Weakest topics
        </h2>
        <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
          {dashboard.weakest_topics.map((topic) => (
            <li key={topic.id}>
              <Link to={`/topics/${topic.id}`} className="block px-4 py-3 hover:bg-slate-50">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 text-sm font-medium break-words">{topic.name}</span>
                  <span className="shrink-0 text-xs text-slate-500">
                    {weaknessLevel(topic.weakness).label} · {percent(topic.weakness)}
                  </span>
                </div>
                <div className="mt-2">
                  <WeaknessMeter name={topic.name} weakness={topic.weakness} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
        <Link to="/practice/topics" className="inline-block text-sm font-medium text-indigo-600 hover:underline">
          All topics
        </Link>
      </section>
    </>
  )
}

function Countdown({ examDate }: { examDate: string | null }) {
  if (examDate === null) return <p className="shrink-0 text-sm text-slate-500">No exam date</p>
  const days = daysUntil(examDate)
  return (
    <div className="shrink-0 text-right">
      <p className="text-xl font-semibold tracking-tight">
        {days < 0 ? 'Passed' : days === 0 ? 'Today' : days === 1 ? '1 day' : `${days} days`}
      </p>
      <p className="text-xs text-slate-500">{formatDate(examDate)}</p>
    </div>
  )
}

/** Shown until there is something to practise: the three steps to get there. */
function GettingStarted({ hasSubjects }: { hasSubjects: boolean }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <p className="font-medium">Nothing to practise yet.</p>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-slate-600">
        <li>
          <Link to="/subjects" className="font-medium text-indigo-600 hover:underline">
            Add a subject
          </Link>{' '}
          with its exam date{hasSubjects && ' (done)'}.
        </li>
        <li>
          <Link to="/exams" className="font-medium text-indigo-600 hover:underline">
            Upload an exam
          </Link>{' '}
          as a PDF, with its solution if you have one.
        </li>
        <li>Check the tasks that were found, and approve the exam.</li>
      </ol>
    </div>
  )
}
