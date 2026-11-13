import { Link, NavLink, Outlet, useParams } from 'react-router'
import { PracticeSession } from '../components/PracticeSession.tsx'
import { Card, ErrorMessage, Loading, PageTitle } from '../components/ui.tsx'
import { useExams, usePracticeTopics } from '../queries.ts'

const modes = [
  { to: '/practice', label: 'Practise now', end: true },
  { to: '/practice/topics', label: 'By topic', end: false },
  { to: '/practice/mock', label: 'Mock exam', end: false },
]

/** The three ways of practising, as tabs. */
export function PracticePage() {
  return (
    <>
      <PageTitle>Practice</PageTitle>
      <nav className="flex gap-1 rounded-lg border border-slate-300 bg-white p-0.5" aria-label="Practice mode">
        {modes.map(({ to, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex min-h-10 flex-1 items-center justify-center rounded-md px-2 text-center text-sm font-medium transition-colors ${
                isActive ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100'
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  )
}

export function PractiseNow() {
  return <PracticeSession />
}

/** Topics, weakest and most urgent first; choosing one starts a session on it. */
export function TopicList() {
  const topics = usePracticeTopics()
  if (topics.isPending) return <Loading />
  if (topics.isError) return <ErrorMessage error={topics.error} />
  if (topics.data.length === 0) {
    return <p className="text-sm text-slate-500">No topics yet. They appear once an exam is approved.</p>
  }
  return (
    <ul className="space-y-2">
      {topics.data.map((topic) => (
        <li key={topic.id}>
          <Link
            to={`/practice/topics/${topic.id}`}
            className="block rounded-xl border border-slate-200 bg-white p-4 shadow-xs transition-colors hover:border-indigo-300"
          >
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-medium break-words">{topic.name}</span>
              <span className="shrink-0 font-mono text-xs text-slate-500">{topic.subject_code}</span>
            </div>
            <div
              className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200"
              role="meter"
              aria-label={`Weakness of ${topic.name}`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(topic.weakness * 100)}
            >
              <div
                className={`h-full rounded-full ${weaknessColour(topic.weakness)}`}
                style={{ width: `${Math.max(2, topic.weakness * 100)}%` }}
              />
            </div>
            <p className="mt-1.5 text-xs text-slate-500">
              {describeWeakness(topic.weakness)} · {topic.attempted_count} of {topic.task_count}{' '}
              {topic.task_count === 1 ? 'task' : 'tasks'} attempted
              {topic.mastery !== null && ` · mastery ${Math.round(topic.mastery * 100)}%`}
            </p>
          </Link>
        </li>
      ))}
    </ul>
  )
}

function weaknessColour(weakness: number): string {
  if (weakness >= 0.66) return 'bg-red-500'
  if (weakness >= 0.33) return 'bg-amber-500'
  return 'bg-emerald-500'
}

function describeWeakness(weakness: number): string {
  if (weakness >= 0.999) return 'Not practised yet'
  if (weakness >= 0.66) return 'Weak'
  if (weakness >= 0.33) return 'Getting there'
  return 'Strong'
}

export function TopicSession() {
  const { topicId = '' } = useParams()
  const topics = usePracticeTopics()
  const topic = topics.data?.find((candidate) => candidate.id === topicId)
  return (
    <>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">{topic?.name ?? 'Topic'}</h2>
        <Link to="/practice/topics" className="text-sm text-indigo-600 hover:underline">
          ← All topics
        </Link>
      </div>
      <PracticeSession topicId={topicId} />
    </>
  )
}

/** Approved exams, any of which can be sat as a mock exam. */
export function MockExamList() {
  const exams = useExams()
  if (exams.isPending) return <Loading />
  if (exams.isError) return <ErrorMessage error={exams.error} />
  const ready = exams.data.filter((exam) => exam.status === 'ready')
  if (ready.length === 0) {
    return <p className="text-sm text-slate-500">No approved exams yet.</p>
  }
  return (
    <>
      <p className="text-sm text-slate-500">
        Sit a whole exam against the clock. You grade yourself against the solutions at the end.
      </p>
      <ul className="space-y-2">
        {ready.map((exam) => (
          <li key={exam.id}>
            <Card className="flex items-center justify-between gap-3">
              <span className="min-w-0 font-medium break-words">
                <span className="font-mono text-sm font-semibold text-indigo-700">{exam.subject_code}</span>{' '}
                {exam.label}
              </span>
              <Link
                to={`/practice/mock/${exam.id}`}
                className="inline-flex min-h-11 shrink-0 items-center rounded-lg bg-indigo-600 px-4 text-sm font-medium text-white hover:bg-indigo-500"
              >
                Start
              </Link>
            </Card>
          </li>
        ))}
      </ul>
    </>
  )
}
