import { useId, useState } from 'react'
import type { MouseEvent, ReactNode } from 'react'
import { pageImageUrl } from '../api.ts'
import type { Exam, Region, Task, Topic } from '../api.ts'
import {
  useApproveExam,
  useDeleteTask,
  useExamTasks,
  useMergeTask,
  useRenameTopic,
  useSplitTask,
  useUpdateTask,
} from '../queries.ts'
import { Button, ErrorMessage, Loading, inputClass } from './ui.tsx'

const MAX_TOPICS = 3

type TaskNode = { task: Task; parts: Task[] }

/** Top-level tasks in document order, each with its sub-tasks. */
function buildTree(tasks: Task[]): TaskNode[] {
  const ids = new Set(tasks.map((task) => task.id))
  const nodes = new Map<string, TaskNode>()
  for (const task of tasks) {
    if (task.parent_id === null || !ids.has(task.parent_id)) nodes.set(task.id, { task, parts: [] })
  }
  for (const task of tasks) {
    if (task.parent_id !== null) nodes.get(task.parent_id)?.parts.push(task)
  }
  return [...nodes.values()]
}

/**
 * The exam's tasks as they were cut out of its pages. While the exam awaits
 * review they can be relabelled, tagged, split, merged and deleted; approving
 * sends them to practice.
 */
export function ReviewPanel({ exam }: { exam: Exam }) {
  const query = useExamTasks(exam)
  const approve = useApproveExam()
  const [selectedId, setSelectedId] = useState<string | null>(null)

  if (query.isPending) return <Loading label="Loading tasks…" />
  if (query.isError) return <ErrorMessage error={query.error} />

  const { tasks, topics } = query.data
  const editable = exam.status === 'needs_review'
  const tree = buildTree(tasks)
  const practisable = tasks.filter((task) => !tasks.some((other) => other.parent_id === task.id))
  const selected = tasks.find((task) => task.id === selectedId) ?? tasks[0]
  const firstId = tasks[0]?.id

  if (tasks.length === 0) {
    return <p className="text-sm text-slate-500">No tasks were found in this exam.</p>
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <p className="text-sm text-slate-600">
          <span className="font-medium text-slate-900">{practisable.length} tasks</span> to practise,
          in {tree.length} {tree.length === 1 ? 'group' : 'groups'}.
          {editable && ' Check that each one is cut in the right place and has a topic.'}
        </p>
        {editable && (
          <Button disabled={approve.isPending} onClick={() => approve.mutate(exam.id)}>
            {approve.isPending ? 'Approving…' : 'Approve all'}
          </Button>
        )}
        {approve.error && (
          <div className="w-full">
            <ErrorMessage error={approve.error} />
          </div>
        )}
      </div>

      <TopicList topics={topics} />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
        <ol className="space-y-4">
          {tree.map(({ task, parts }) => (
            <li
              key={task.id}
              className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs"
            >
              <TaskCard
                task={task}
                exam={exam}
                topics={topics}
                editable={editable}
                hasParts={parts.length > 0}
                isFirst={task.id === firstId}
                selected={selected?.id === task.id}
                onSelect={() => setSelectedId(task.id)}
              />
              {parts.length > 0 && (
                <ol className="divide-y divide-slate-200 border-t border-slate-200">
                  {parts.map((part) => (
                    <li key={part.id} className="border-l-4 border-l-indigo-200">
                      <TaskCard
                        task={part}
                        parent={task}
                        exam={exam}
                        topics={topics}
                        editable={editable}
                        hasParts={false}
                        isFirst={false}
                        selected={selected?.id === part.id}
                        onSelect={() => setSelectedId(part.id)}
                      />
                    </li>
                  ))}
                </ol>
              )}
            </li>
          ))}
        </ol>

        {/* Beside the list on a wide screen: the original page of the selected task. */}
        <aside className="sticky top-16 hidden max-h-[calc(100dvh-5rem)] space-y-2 overflow-y-auto lg:block">
          {selected && (
            <>
              <p className="text-xs font-medium tracking-wide text-slate-500 uppercase">
                Task {selected.number} on the original page
              </p>
              <PagePreview exam={exam} regions={selected.regions} />
            </>
          )}
        </aside>
      </div>
    </div>
  )
}

/**
 * The subject's topics, each of which can be renamed. Topics start out named
 * after task titles ("Normalfordelte kulediametere"); this is where they are
 * given proper names and where duplicates are merged.
 */
function TopicList({ topics }: { topics: Topic[] }) {
  const rename = useRenameTopic()
  if (topics.length === 0) return null
  return (
    <details className="rounded-xl border border-slate-200 bg-white p-4">
      <summary className="cursor-pointer text-sm font-medium text-slate-700">
        Topics in this subject ({topics.length})
      </summary>
      <p className="mt-2 text-sm text-slate-500">
        Renaming a topic changes it on every task, in every exam. Give two topics the same name to
        merge them.
      </p>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {topics.map((topic) => (
          <li key={topic.id}>
            <TextField
              label={`Topic ${topic.name}`}
              hideLabel
              value={topic.name}
              onSave={(name) => name && rename.mutate({ topicId: topic.id, name })}
            />
          </li>
        ))}
      </ul>
      <div className="mt-2">
        <ErrorMessage error={rename.error} />
      </div>
    </details>
  )
}

type TaskCardProps = {
  task: Task
  parent?: Task
  exam: Exam
  topics: Topic[]
  editable: boolean
  hasParts: boolean
  isFirst: boolean
  selected: boolean
  onSelect: () => void
}

function TaskCard({ task, parent, exam, topics, editable, hasParts, isFirst, selected, onSelect }: TaskCardProps) {
  const update = useUpdateTask(exam.id)
  const remove = useDeleteTask(exam.id)
  const merge = useMergeTask(exam.id)
  const split = useSplitTask(exam.id)
  const [splitting, setSplitting] = useState(false)
  const [showSolution, setShowSolution] = useState(false)
  const [showPage, setShowPage] = useState(false)

  const busy = update.isPending || remove.isPending || merge.isPending || split.isPending
  const error = update.error ?? remove.error ?? merge.error ?? split.error
  const save = (changes: Parameters<typeof update.mutate>[0]['changes']) =>
    update.mutate({ taskId: task.id, changes })
  const hasSolution = task.solution_images.length > 0 || Boolean(task.solution_text)

  return (
    <article
      onClick={onSelect}
      onFocus={onSelect}
      aria-label={`Task ${task.number}`}
      className={`space-y-3 p-4 ${selected ? 'lg:bg-indigo-50/40' : ''}`}
    >
      <div className="flex flex-wrap items-end gap-2">
        {editable ? (
          <>
            <TextField
              label="Number"
              value={task.number}
              className="w-20"
              inputClassName="font-mono font-semibold"
              onSave={(number) => number && save({ number })}
            />
            {!parent && (
              <TextField
                label="Title"
                value={task.title ?? ''}
                className="min-w-40 flex-1"
                onSave={(title) => save({ title: title || null })}
              />
            )}
            <TextField
              label="Points"
              value={task.points === null ? '' : String(task.points)}
              inputMode="decimal"
              className="w-20"
              onSave={(text) => {
                const points = text === '' ? null : Number(text.replace(',', '.'))
                if (points === null || (Number.isFinite(points) && points >= 0)) save({ points })
              }}
            />
          </>
        ) : (
          <h3 className="text-base font-semibold">
            <span className="font-mono text-indigo-700">{task.number}</span> {task.title}
            {task.points !== null && (
              <span className="ml-2 text-sm font-normal text-slate-500">{task.points} p</span>
            )}
          </h3>
        )}
      </div>

      <TopicEditor
        task={task}
        parent={parent}
        topics={topics}
        editable={editable}
        needsTopic={!hasParts}
        onChange={(names) => save({ topics: names })}
      />

      <TaskImages
        images={task.images}
        alt={`Task ${task.number}`}
        onSplit={
          splitting
            ? (imageIndex, fraction) => {
                setSplitting(false)
                split.mutate({ taskId: task.id, imageIndex, fraction })
              }
            : undefined
        }
      />
      {splitting && (
        <p className="text-sm text-indigo-700">
          Click in the task where the next one should begin.
        </p>
      )}

      <ErrorMessage error={error} />

      <div className="flex flex-wrap gap-2">
        {hasSolution && (
          <SmallButton pressed={showSolution} onClick={() => setShowSolution((shown) => !shown)}>
            {showSolution ? 'Hide solution' : 'Show solution'}
          </SmallButton>
        )}
        <span className="lg:hidden">
          <SmallButton pressed={showPage} onClick={() => setShowPage((shown) => !shown)}>
            {showPage ? 'Hide page' : 'Show on page'}
          </SmallButton>
        </span>
        {editable && (
          <>
            <SmallButton pressed={splitting} disabled={busy} onClick={() => setSplitting((on) => !on)}>
              {splitting ? 'Cancel split' : 'Split'}
            </SmallButton>
            {!hasParts && !isFirst && (
              <SmallButton disabled={busy} onClick={() => merge.mutate(task.id)}>
                Merge with previous
              </SmallButton>
            )}
            <SmallButton
              danger
              disabled={busy}
              onClick={() => {
                const what = hasParts ? `task ${task.number} and its sub-tasks` : `task ${task.number}`
                if (window.confirm(`Delete ${what}?`)) remove.mutate(task.id)
              }}
            >
              Delete
            </SmallButton>
          </>
        )}
      </div>

      {showSolution && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-2">
          <p className="mb-1 text-xs font-medium tracking-wide text-emerald-800 uppercase">Solution</p>
          {task.solution_images.length > 0 ? (
            <TaskImages images={task.solution_images} alt={`Solution to task ${task.number}`} />
          ) : (
            <p className="text-sm whitespace-pre-wrap">{task.solution_text}</p>
          )}
        </div>
      )}
      {showPage && (
        <div className="lg:hidden">
          <PagePreview exam={exam} regions={task.regions} />
        </div>
      )}
    </article>
  )
}

type TaskImagesProps = {
  images: string[]
  alt: string
  /** When given, the images take a click as "split here". */
  onSplit?: (imageIndex: number, fraction: number) => void
}

/** A task's images stacked into one picture; a part that crosses a page break has two. */
function TaskImages({ images, alt, onSplit }: TaskImagesProps) {
  const [guide, setGuide] = useState<{ index: number; fraction: number } | null>(null)
  if (images.length === 0) {
    return <p className="text-sm text-slate-400 italic">Nothing was found for this task.</p>
  }

  const fractionAt = (event: MouseEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    return Math.min(0.98, Math.max(0.02, (event.clientY - box.top) / box.height))
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      {images.map((url, index) => (
        <div
          key={url}
          className={`relative ${index > 0 ? 'border-t border-dashed border-slate-200' : ''} ${
            onSplit ? 'cursor-row-resize' : ''
          }`}
          onMouseMove={onSplit && ((event) => setGuide({ index, fraction: fractionAt(event) }))}
          onMouseLeave={onSplit && (() => setGuide(null))}
          onClick={
            onSplit &&
            ((event) => {
              event.stopPropagation()
              setGuide(null)
              onSplit(index, fractionAt(event))
            })
          }
        >
          <img
            src={url}
            alt={images.length > 1 ? `${alt}, part ${index + 1}` : alt}
            loading="lazy"
            className="block h-auto w-full"
          />
          {onSplit && guide?.index === index && (
            <div
              className="pointer-events-none absolute inset-x-0 border-t-2 border-indigo-600"
              style={{ top: `${guide.fraction * 100}%` }}
            />
          )}
        </div>
      ))}
    </div>
  )
}

/** The pages a task is on, with the task's regions marked. */
function PagePreview({ exam, regions }: { exam: Exam; regions: Region[] }) {
  const pages = [...new Set(regions.map((region) => region.page))].sort((a, b) => a - b)
  if (pages.length === 0) return <p className="text-sm text-slate-400">No page to show.</p>
  return (
    <div className="space-y-2">
      {pages.map((page) => (
        <figure key={page}>
          <div className="relative overflow-hidden rounded-lg border border-slate-200 bg-white">
            <img
              src={pageImageUrl(exam.id, 'exam', page)}
              alt={`Exam page ${page}`}
              width={1240}
              height={1754}
              loading="lazy"
              className="block h-auto w-full"
            />
            {regions
              .filter((region) => region.page === page)
              .map((region) => (
                <div
                  key={`${region.top}-${region.bottom}`}
                  className="pointer-events-none absolute border-2 border-indigo-500 bg-indigo-400/15"
                  style={{
                    top: `${region.top * 100}%`,
                    height: `${(region.bottom - region.top) * 100}%`,
                    left: `${region.left * 100}%`,
                    width: `${(region.right - region.left) * 100}%`,
                  }}
                />
              ))}
          </div>
          <figcaption className="mt-1 text-xs text-slate-500">
            Page {page} of {exam.page_count}
          </figcaption>
        </figure>
      ))}
    </div>
  )
}

type TopicEditorProps = {
  task: Task
  parent?: Task
  topics: Topic[]
  editable: boolean
  /** Whether this task is practised itself and so must end up with a topic. */
  needsTopic: boolean
  onChange: (names: string[]) => void
}

function TopicEditor({ task, parent, topics, editable, needsTopic, onChange }: TopicEditorProps) {
  const [draft, setDraft] = useState('')
  const listId = useId()
  const own = task.topics.map((topic) => topic.name)
  const inherited = own.length === 0 ? (parent?.topics ?? []) : []
  const missing = needsTopic && own.length === 0 && inherited.length === 0

  const add = () => {
    const name = draft.trim()
    setDraft('')
    if (name && !own.some((existing) => existing.toLowerCase() === name.toLowerCase())) {
      onChange([...own, name])
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5" onClick={(event) => event.stopPropagation()}>
      {task.topics.map((topic) => (
        <span
          key={topic.id}
          className="inline-flex items-center gap-1 rounded-full bg-indigo-100 py-0.5 pr-1 pl-2.5 text-sm text-indigo-800"
        >
          {topic.name}
          {editable && (
            <button
              type="button"
              aria-label={`Remove topic ${topic.name}`}
              onClick={() => onChange(own.filter((name) => name !== topic.name))}
              className="flex size-6 items-center justify-center rounded-full hover:bg-indigo-200"
            >
              ×
            </button>
          )}
        </span>
      ))}
      {inherited.map((topic) => (
        <span
          key={topic.id}
          title={`From task ${parent?.number}`}
          className="rounded-full border border-dashed border-slate-300 px-2.5 py-0.5 text-sm text-slate-500"
        >
          {topic.name}
        </span>
      ))}
      {missing && (
        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-sm text-amber-800">
          Needs a topic
        </span>
      )}
      {editable && own.length < MAX_TOPICS && (
        <form
          className="flex items-center gap-1"
          onSubmit={(event) => {
            event.preventDefault()
            add()
          }}
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            list={listId}
            placeholder="Add topic"
            aria-label={`Add a topic to task ${task.number}`}
            maxLength={200}
            className="min-h-9 w-36 rounded-lg border border-slate-300 bg-white px-2 text-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-2 focus:outline-indigo-500/30"
          />
          <datalist id={listId}>
            {topics
              .filter((topic) => !own.includes(topic.name))
              .map((topic) => (
                <option key={topic.id} value={topic.name} />
              ))}
          </datalist>
          {draft.trim() && (
            <button
              type="submit"
              className="min-h-9 rounded-lg bg-indigo-600 px-3 text-sm font-medium text-white hover:bg-indigo-500"
            >
              Add
            </button>
          )}
        </form>
      )}
    </div>
  )
}

type TextFieldProps = {
  label: string
  value: string
  /** Keep the label for screen readers only. */
  hideLabel?: boolean
  className?: string
  inputClassName?: string
  inputMode?: 'decimal'
  /** Called with the trimmed text when the field loses focus or Enter is pressed, if it changed. */
  onSave: (value: string) => void
}

/**
 * A small labelled input that saves when left. It is re-created whenever the
 * saved value changes, so it always starts from what the server has.
 */
function TextField(props: TextFieldProps) {
  return <TextFieldInput key={props.value} {...props} />
}

function TextFieldInput({
  label,
  hideLabel = false,
  value,
  className = '',
  inputClassName = '',
  inputMode,
  onSave,
}: TextFieldProps) {
  const [draft, setDraft] = useState(value)

  const commit = () => {
    const next = draft.trim()
    if (next !== value) onSave(next)
    else setDraft(value)
  }

  return (
    <label className={`block ${className}`}>
      <span className={hideLabel ? 'sr-only' : 'mb-0.5 block text-xs text-slate-500'}>{label}</span>
      <input
        value={draft}
        inputMode={inputMode}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur()
          if (event.key === 'Escape') setDraft(value)
        }}
        className={`${inputClass} min-h-10 px-2 ${inputClassName}`}
      />
    </label>
  )
}

type SmallButtonProps = {
  children: ReactNode
  onClick: () => void
  disabled?: boolean
  pressed?: boolean
  danger?: boolean
}

function SmallButton({ children, onClick, disabled, pressed, danger }: SmallButtonProps) {
  const tone = danger
    ? 'border-red-200 text-red-700 hover:bg-red-50'
    : pressed
      ? 'border-indigo-600 bg-indigo-600 text-white'
      : 'border-slate-300 text-slate-700 hover:bg-slate-50'
  return (
    <button
      type="button"
      disabled={disabled}
      aria-pressed={pressed}
      onClick={(event) => {
        event.stopPropagation()
        onClick()
      }}
      className={`min-h-10 rounded-lg border px-3 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${tone}`}
    >
      {children}
    </button>
  )
}
