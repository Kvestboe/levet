import { useMutation } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { api } from '../api.ts'
import type { Grade, PracticeTask } from '../api.ts'
import { GradeButtons, Solution, TaskBody, TaskHeading } from '../components/practice.tsx'
import { Button, ErrorMessage, Loading } from '../components/ui.tsx'
import { GRADES, formatDuration, gradeLabel, gradeScore, isTyping } from '../practice.ts'
import { useMockExamTasks } from '../queries.ts'

export function MockExamPage() {
  const { examId = '' } = useParams()
  const tasks = useMockExamTasks(examId)
  if (tasks.isPending) return <Loading label="Preparing the exam…" />
  if (tasks.isError) return <ErrorMessage error={tasks.error} />
  if (tasks.data.length === 0) return <p className="text-sm text-slate-500">This exam has no tasks.</p>
  return <MockExam tasks={tasks.data} />
}

type Phase = 'working' | 'grading' | 'done'

/**
 * A whole exam in one sitting: work through every task against the clock,
 * then go through them again with the solutions and grade yourself. Nothing
 * is saved until the grades are handed in.
 */
function MockExam({ tasks }: { tasks: PracticeTask[] }) {
  const [phase, setPhase] = useState<Phase>('working')
  const [index, setIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [grades, setGrades] = useState<Record<string, Grade>>({})
  const [clock, setClock] = useState<{ total: number; perTask: Record<string, number> }>({
    total: 0,
    perTask: {},
  })

  const task = tasks[index]
  const exam = tasks[0].exam

  // The clock runs while working, and credits each second to the task on screen.
  useEffect(() => {
    if (phase !== 'working') return
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return
      setClock((current) => ({
        total: current.total + 1,
        perTask: { ...current.perTask, [task.id]: (current.perTask[task.id] ?? 0) + 1 },
      }))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [phase, task.id])

  const save = useMutation({
    mutationFn: async () => {
      for (const each of tasks) {
        await api.recordAttempt({
          task_id: each.id,
          grade: grades[each.id],
          time_spent_seconds: clock.perTask[each.id] ?? 0,
          answer: answers[each.id]?.trim() || undefined,
          note: `Mock exam ${exam.label}`,
        })
      }
    },
    onSuccess: () => setPhase('done'),
  })

  const gradedCount = tasks.filter((each) => grades[each.id]).length
  const setGrade = (grade: Grade) => {
    setGrades((current) => ({ ...current, [task.id]: grade }))
    // Move on to the next task that still needs a grade.
    const next = tasks.findIndex((each, position) => position > index && !grades[each.id])
    if (next !== -1) setIndex(next)
  }

  // While grading, 1-4 grade the task on screen.
  useEffect(() => {
    if (phase !== 'grading') return
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event) || event.ctrlKey || event.metaKey || event.altKey) return
      if (['1', '2', '3', '4'].includes(event.key)) {
        event.preventDefault()
        setGrade(GRADES[Number(event.key) - 1].grade)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  if (phase === 'done') return <Result tasks={tasks} grades={grades} seconds={clock.total} />

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">
          Mock exam · <span className="font-mono text-indigo-700">{exam.subject_code}</span> {exam.label}
        </h2>
        <span className="font-mono text-sm text-slate-600 tabular-nums" aria-label="Time used">
          {formatDuration(clock.total)}
        </span>
      </div>

      <nav className="flex flex-wrap gap-1.5" aria-label="Tasks">
        {tasks.map((each, position) => {
          const marked = phase === 'grading' ? Boolean(grades[each.id]) : Boolean(answers[each.id]?.trim())
          return (
            <button
              key={each.id}
              type="button"
              aria-current={position === index}
              onClick={() => setIndex(position)}
              className={`min-h-10 min-w-10 rounded-lg border px-2 font-mono text-sm transition-colors ${
                position === index
                  ? 'border-indigo-600 bg-indigo-600 text-white'
                  : marked
                    ? 'border-emerald-300 bg-emerald-50 text-emerald-800'
                    : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
              }`}
            >
              {each.number}
            </button>
          )
        })}
      </nav>

      <article className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-xs sm:p-5">
        <TaskHeading task={task} />
        <TaskBody key={task.id} task={task} />

        {phase === 'working' ? (
          <textarea
            value={answers[task.id] ?? ''}
            onChange={(event) => setAnswers((current) => ({ ...current, [task.id]: event.target.value }))}
            rows={3}
            aria-label={`Your answer to task ${task.number}`}
            placeholder="Your answer (optional)"
            className="block w-full rounded-lg border border-slate-300 bg-white p-3 text-base placeholder:text-slate-400 focus:border-indigo-500 focus:outline-2 focus:outline-indigo-500/30"
          />
        ) : (
          <>
            {answers[task.id]?.trim() && (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <p className="mb-1 text-xs font-medium tracking-wide text-slate-500 uppercase">Your answer</p>
                <p className="text-sm whitespace-pre-wrap">{answers[task.id]}</p>
              </div>
            )}
            <Solution task={task} />
            <GradeButtons onGrade={setGrade} selected={grades[task.id] ?? null} disabled={save.isPending} />
          </>
        )}

        <div className="flex justify-between gap-2">
          <Button variant="secondary" disabled={index === 0} onClick={() => setIndex(index - 1)}>
            Previous
          </Button>
          <Button
            variant="secondary"
            disabled={index === tasks.length - 1}
            onClick={() => setIndex(index + 1)}
          >
            Next
          </Button>
        </div>
      </article>

      {phase === 'working' ? (
        <Button
          className="w-full"
          onClick={() => {
            if (window.confirm('Finish the exam and go on to grading?')) {
              setIndex(0)
              setPhase('grading')
            }
          }}
        >
          Finish and grade
        </Button>
      ) : (
        <div className="space-y-2">
          <ErrorMessage error={save.error} />
          <Button
            className="w-full"
            disabled={gradedCount < tasks.length || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending
              ? 'Saving…'
              : gradedCount < tasks.length
                ? `Grade every task to finish (${gradedCount} of ${tasks.length})`
                : 'Save results'}
          </Button>
        </div>
      )}
    </div>
  )
}

type ResultProps = {
  tasks: PracticeTask[]
  grades: Record<string, Grade>
  seconds: number
}

function Result({ tasks, grades, seconds }: ResultProps) {
  // A task without points counts as one.
  const worth = (task: PracticeTask) => task.points ?? 1
  const available = tasks.reduce((sum, task) => sum + worth(task), 0)
  const earned = tasks.reduce((sum, task) => sum + worth(task) * gradeScore(grades[task.id]), 0)
  const percent = available > 0 ? Math.round((earned / available) * 100) : 0

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center shadow-xs">
        <p className="text-sm text-slate-500">
          <span className="font-mono">{tasks[0].exam.subject_code}</span> {tasks[0].exam.label}
        </p>
        <p className="mt-2 text-5xl font-semibold tracking-tight text-indigo-700">{percent}%</p>
        <p className="mt-2 text-sm text-slate-600">
          {formatNumber(earned)} of {formatNumber(available)} points · {formatDuration(seconds)}
        </p>
      </div>
      <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
        {tasks.map((task) => (
          <li key={task.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
            <span>
              Task <span className="font-mono font-semibold">{task.number}</span>
              {task.title && <span className="text-slate-500"> · {task.title}</span>}
            </span>
            <span className="shrink-0 font-medium">{gradeLabel(grades[task.id])}</span>
          </li>
        ))}
      </ul>
      <Link to="/practice" className="inline-block text-sm font-medium text-indigo-600 hover:underline">
        Back to practice
      </Link>
    </div>
  )
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}
