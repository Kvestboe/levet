import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import type { AttemptInput, Grade, QueueEntry } from '../api.ts'
import { GRADES, describeDue, formatDuration, gradeLabel, isTyping, useStopwatch } from '../practice.ts'
import { usePracticeQueue, useRecordAttempt } from '../queries.ts'
import { GradeButtons, ReasonBadge, Solution, TaskBody, TaskHeading } from './practice.tsx'
import { Button, ErrorMessage, Loading } from './ui.tsx'

type LastAttempt = { number: string; grade: Grade; due: string }

/**
 * One task at a time from the head of the practice queue: read it, reveal the
 * solution, grade yourself, on to the next. With `topicId`, only that topic.
 */
export function PracticeSession({ topicId }: { topicId?: string }) {
  const queue = usePracticeQueue(topicId)
  const record = useRecordAttempt()
  const [last, setLast] = useState<LastAttempt | null>(null)

  if (queue.isPending) return <Loading label="Finding what to practise…" />
  if (queue.isError) return <ErrorMessage error={queue.error} />

  const entry = queue.data.entries[0]
  if (!entry) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <p className="font-medium">Nothing to practise yet.</p>
        <p className="mt-1 text-sm text-slate-500">
          Tasks appear here once an exam has been uploaded and approved.
        </p>
        <Link to="/exams" className="mt-3 inline-block text-sm font-medium text-indigo-600 hover:underline">
          Go to exams
        </Link>
      </div>
    )
  }

  const grade = (attempt: AttemptInput) =>
    record.mutate(attempt, {
      onSuccess: (result) => {
        setLast({ number: entry.task.number, grade: result.grade, due: result.due })
        void queue.refetch()
      },
    })

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500" aria-live="polite">
        {queue.data.due_count > 0 && (
          <span className="font-medium text-red-700">{queue.data.due_count} due again · </span>
        )}
        {queue.data.total} {queue.data.total === 1 ? 'task' : 'tasks'} in the queue
        {last && (
          <span>
            {' '}
            · Task {last.number} graded {gradeLabel(last.grade)}, back {describeDue(last.due)}
          </span>
        )}
      </p>
      <PracticeCard
        // A new task, or the same one coming round again, starts from scratch.
        key={`${entry.task.id}:${entry.task.attempt_count}`}
        entry={entry}
        busy={record.isPending || queue.isFetching}
        error={record.error}
        onGrade={grade}
      />
    </div>
  )
}

type PracticeCardProps = {
  entry: QueueEntry
  busy: boolean
  error: Error | null
  onGrade: (attempt: AttemptInput) => void
}

function PracticeCard({ entry, busy, error, onGrade }: PracticeCardProps) {
  const { task, reason } = entry
  const [revealed, setRevealed] = useState(false)
  const [answer, setAnswer] = useState('')
  const [note, setNote] = useState('')
  const [showTimer, setShowTimer] = useState(true)
  // The clock stops when the solution is shown: reading it is not solving time.
  const seconds = useStopwatch(task.id, !revealed)

  const grade = (chosen: Grade) => {
    if (busy) return
    onGrade({
      task_id: task.id,
      grade: chosen,
      time_spent_seconds: seconds,
      answer: answer.trim() || undefined,
      note: note.trim() || undefined,
    })
  }

  // Space reveals the solution; 1-4 grade. Keys typed into a text field are left alone.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event) || event.ctrlKey || event.metaKey || event.altKey) return
      if (!revealed && event.code === 'Space') {
        event.preventDefault()
        setRevealed(true)
      } else if (revealed && ['1', '2', '3', '4'].includes(event.key)) {
        event.preventDefault()
        grade(GRADES[Number(event.key) - 1].grade)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <article className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-xs sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <TaskHeading task={task}>
          <ReasonBadge reason={reason} />
        </TaskHeading>
        <button
          type="button"
          onClick={() => setShowTimer((shown) => !shown)}
          aria-label={showTimer ? 'Hide timer' : 'Show timer'}
          className="min-h-10 shrink-0 rounded-lg px-2 font-mono text-sm text-slate-500 tabular-nums hover:bg-slate-100"
        >
          {showTimer ? formatDuration(seconds) : 'Timer'}
        </button>
      </div>

      <TaskBody task={task} />

      <details>
        <summary className="min-h-10 cursor-pointer py-2 text-sm font-medium text-slate-600">
          Write an answer (optional)
        </summary>
        <textarea
          value={answer}
          onChange={(event) => setAnswer(event.target.value)}
          rows={4}
          aria-label="Your answer"
          placeholder="Your answer, for your own record"
          className="mt-1 block w-full rounded-lg border border-slate-300 bg-white p-3 text-base placeholder:text-slate-400 focus:border-indigo-500 focus:outline-2 focus:outline-indigo-500/30"
        />
      </details>

      {!revealed ? (
        <Button className="min-h-14 w-full text-base" onClick={() => setRevealed(true)}>
          {task.solution ? 'Show solution' : 'Done — grade myself'}
          <kbd className="ml-2 hidden rounded border border-white/40 px-1.5 text-xs font-normal sm:inline">
            space
          </kbd>
        </Button>
      ) : (
        <>
          <Solution task={task} />
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            aria-label="Note"
            placeholder="Note to self (optional)"
            maxLength={5000}
            className="block min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base placeholder:text-slate-400 focus:border-indigo-500 focus:outline-2 focus:outline-indigo-500/30"
          />
          <ErrorMessage error={error} />
          <GradeButtons onGrade={grade} disabled={busy} />
        </>
      )}
    </article>
  )
}
