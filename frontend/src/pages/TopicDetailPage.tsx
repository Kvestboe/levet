import { Link, useParams } from 'react-router'
import type { TopicDetail } from '../api.ts'
import { MasteryChart } from '../components/MasteryChart.tsx'
import { StatTile, WeaknessMeter } from '../components/progress.tsx'
import { ErrorMessage, Loading, PageTitle } from '../components/ui.tsx'
import { formatDateTime } from '../format.ts'
import { describeDue, formatDuration, gradeLabel } from '../practice.ts'
import { percent, weaknessLevel } from '../progress.ts'
import { useTopicDetail } from '../queries.ts'

export function TopicDetailPage() {
  const { topicId = '' } = useParams()
  const detail = useTopicDetail(topicId)
  return (
    <>
      <Link to="/practice/topics" className="inline-flex min-h-11 items-center text-sm text-indigo-600 hover:underline">
        ← All topics
      </Link>
      {detail.isPending ? (
        <Loading />
      ) : detail.isError ? (
        <ErrorMessage error={detail.error} />
      ) : (
        <Detail detail={detail.data} fetchedAt={detail.dataUpdatedAt} />
      )}
    </>
  )
}

function Detail({ detail, fetchedAt }: { detail: TopicDetail; fetchedAt: number }) {
  const { topic, history, tasks, attempts } = detail
  // "Due in 3 days" is counted from when these figures were fetched.
  const now = new Date(fetchedAt)
  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <PageTitle>{topic.name}</PageTitle>
          <p className="mt-1 font-mono text-sm text-slate-500">{topic.subject_code}</p>
        </div>
        <Link
          to={`/practice/topics/${topic.id}`}
          className="inline-flex min-h-11 shrink-0 items-center rounded-lg bg-indigo-600 px-4 text-sm font-medium text-white hover:bg-indigo-500"
        >
          Practise this topic
        </Link>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile
          label="Weakness"
          value={percent(topic.weakness)}
          detail={
            <div className="space-y-1.5">
              <p>{weaknessLevel(topic.weakness).label}</p>
              <WeaknessMeter name={topic.name} weakness={topic.weakness} />
            </div>
          }
        />
        <StatTile
          label="Mastery"
          value={topic.mastery === null ? '–' : percent(topic.mastery)}
          detail="Recent attempts count the most"
        />
        <StatTile
          label="Tasks attempted"
          value={topic.attempted_count}
          detail={`of ${topic.task_count} in this topic`}
        />
      </div>

      <section aria-labelledby="mastery-heading" className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
        <h2 id="mastery-heading" className="text-base font-semibold">
          Mastery over time
        </h2>
        <p className="mb-3 text-sm text-slate-500">How well this topic's tasks went, at the end of each day.</p>
        <MasteryChart history={history} />
      </section>

      <section aria-labelledby="tasks-heading" className="space-y-2">
        <h2 id="tasks-heading" className="text-base font-semibold">
          Tasks
        </h2>
        <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
          {tasks.map((task) => (
            <li key={task.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
              <span className="min-w-0">
                <span className="text-slate-500">{task.exam.label} · </span>
                Task <span className="font-mono font-semibold">{task.number}</span>
              </span>
              <span className="shrink-0 text-right text-slate-600">
                {task.last_grade === null ? (
                  <span className="text-slate-400">Not attempted</span>
                ) : (
                  <>
                    {gradeLabel(task.last_grade)}
                    <span className="text-slate-400">
                      {' '}
                      · {task.attempt_count}× ·{' '}
                      {task.due && new Date(task.due) > now ? `due ${describeDue(task.due, now)}` : 'due now'}
                    </span>
                  </>
                )}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="attempts-heading" className="space-y-2">
        <h2 id="attempts-heading" className="text-base font-semibold">
          Attempts
        </h2>
        {attempts.length === 0 ? (
          <p className="text-sm text-slate-500">None yet.</p>
        ) : (
          <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
            {attempts.map((attempt) => (
              <li key={attempt.id} className="px-4 py-2.5 text-sm">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-medium">
                    {gradeLabel(attempt.grade)}
                    <span className="font-normal text-slate-500">
                      {' '}
                      · {attempt.exam_label}, task <span className="font-mono">{attempt.task_number}</span>
                    </span>
                  </span>
                  <span className="shrink-0 text-xs text-slate-500">
                    {attempt.time_spent_seconds !== null && `${formatDuration(attempt.time_spent_seconds)} · `}
                    {formatDateTime(attempt.attempted_at)}
                  </span>
                </div>
                {attempt.answer && <p className="mt-1 whitespace-pre-wrap text-slate-700">{attempt.answer}</p>}
                {attempt.note && <p className="mt-1 text-slate-500 italic">{attempt.note}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
