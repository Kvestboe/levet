// Building blocks shared by the practice modes: showing a task, its solution
// and the four grade buttons.

import { useState } from 'react'
import type { ReactNode } from 'react'
import type { Grade, PracticeTask, Reason } from '../api.ts'
import { GRADES } from '../practice.ts'

type GradeButtonsProps = {
  onGrade: (grade: Grade) => void
  disabled?: boolean
  selected?: Grade | null
  /** Show the 1-4 keyboard hints (the keys themselves are handled by the caller). */
  showKeys?: boolean
}

/** The four self-grades. Tall buttons, two by two on a phone. */
export function GradeButtons({ onGrade, disabled, selected, showKeys = true }: GradeButtonsProps) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="group" aria-label="Grade yourself">
      {GRADES.map(({ grade, label, hint, className }, index) => (
        <button
          key={grade}
          type="button"
          disabled={disabled}
          aria-pressed={selected === undefined ? undefined : selected === grade}
          onClick={() => onGrade(grade)}
          className={`flex min-h-16 flex-col items-center justify-center rounded-xl border-2 px-2 py-2 text-center transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${className} ${
            selected === grade ? 'ring-2 ring-slate-900 ring-offset-2' : ''
          }`}
        >
          <span className="text-base font-semibold">
            {label}
            {showKeys && (
              <kbd className="ml-2 hidden rounded border border-current/30 px-1.5 text-xs font-normal opacity-70 sm:inline">
                {index + 1}
              </kbd>
            )}
          </span>
          <span className="text-xs opacity-80">{hint}</span>
        </button>
      ))}
    </div>
  )
}

const reasonStyles: Record<Reason, { label: string; className: string }> = {
  due: { label: 'Due again', className: 'bg-red-100 text-red-800' },
  new: { label: 'New', className: 'bg-sky-100 text-sky-800' },
  weak: { label: 'Weak topic', className: 'bg-amber-100 text-amber-800' },
}

export function ReasonBadge({ reason }: { reason: Reason }) {
  const { label, className } = reasonStyles[reason]
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>
      {label}
    </span>
  )
}

/** Where a task comes from and what it is about. */
export function TaskHeading({ task, children }: { task: PracticeTask; children?: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h2 className="text-lg font-semibold">
          Task <span className="font-mono text-indigo-700">{task.number}</span>
          {task.title && <span className="font-normal text-slate-600"> · {task.title}</span>}
        </h2>
        {children}
      </div>
      <p className="text-sm text-slate-500">
        <span className="font-mono">{task.exam.subject_code}</span> {task.exam.label}
        {task.points !== null && ` · ${task.points} ${task.points === 1 ? 'point' : 'points'}`}
        {task.attempt_count > 0 &&
          ` · attempted ${task.attempt_count === 1 ? 'once' : `${task.attempt_count} times`}`}
      </p>
      {task.topics.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {task.topics.map((topic) => (
            <span key={topic.id} className="rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs text-indigo-800">
              {topic.name}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * A task's images stacked into one picture. A page shrunk to a phone's width
 * is hard to read, so tapping the picture doubles its size (it then scrolls
 * sideways); tapping again fits it back.
 */
function Images({ images, alt }: { images: string[]; alt: string }) {
  const [zoomed, setZoomed] = useState(false)
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <div
        onClick={() => setZoomed((on) => !on)}
        title={zoomed ? 'Click to fit to width' : 'Click to enlarge'}
        className={zoomed ? 'w-[200%] cursor-zoom-out' : 'w-full cursor-zoom-in'}
      >
        {images.map((url, index) => (
          <img
            key={url}
            src={url}
            alt={images.length > 1 ? `${alt}, part ${index + 1}` : alt}
            className={`block h-auto w-full ${index > 0 ? 'border-t border-dashed border-slate-200' : ''}`}
          />
        ))}
      </div>
    </div>
  )
}

/**
 * The task as printed. A part of a larger task is shown under that task's
 * introduction; "Show whole task" brings in the other parts too, for when the
 * information needed sits in one of them.
 */
export function TaskBody({ task }: { task: PracticeTask }) {
  const [whole, setWhole] = useState(false)
  const hasMore = task.group.length > (task.context ? 2 : 1)

  return (
    <div className="space-y-2">
      {whole ? (
        task.group.map((part) => (
          <div
            key={part.id}
            className={part.id === task.id ? 'rounded-xl ring-2 ring-indigo-400 ring-offset-2' : 'opacity-80'}
          >
            {part.images.length > 0 && <Images images={part.images} alt={`Task ${part.number}`} />}
          </div>
        ))
      ) : (
        <>
          {task.context && task.context.images.length > 0 && (
            <Images images={task.context.images} alt={`Introduction to task ${task.context.number}`} />
          )}
          {task.images.length > 0 ? (
            <Images images={task.images} alt={`Task ${task.number}`} />
          ) : (
            <p className="text-sm text-slate-400 italic">This task has no image.</p>
          )}
        </>
      )}
      {hasMore && (
        <button
          type="button"
          onClick={() => setWhole((shown) => !shown)}
          className="min-h-10 text-sm font-medium text-indigo-600 hover:underline"
        >
          {whole ? 'Show only this part' : `Show whole task ${task.context?.number ?? ''}`}
        </button>
      )}
    </div>
  )
}

export function Solution({ task }: { task: PracticeTask }) {
  const solution = task.solution
  return (
    <section className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-3" aria-label="Solution">
      <h3 className="mb-2 text-xs font-medium tracking-wide text-emerald-800 uppercase">Solution</h3>
      {solution === null ? (
        <p className="text-sm text-slate-600">There is no solution for this task. Grade yourself as best you can.</p>
      ) : solution.images.length > 0 ? (
        <Images images={solution.images} alt={`Solution to task ${task.number}`} />
      ) : (
        <p className="text-sm whitespace-pre-wrap">{solution.text}</p>
      )}
    </section>
  )
}
