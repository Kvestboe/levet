import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { pageImageUrl } from '../api.ts'
import type { Exam, PageKind } from '../api.ts'
import { FailedExam } from '../components/FailedExam.tsx'
import { ReviewPanel } from '../components/ReviewPanel.tsx'
import { ErrorMessage, Loading, PageTitle, ProcessingProgress, StatusBadge } from '../components/ui.tsx'
import { formatDateTime } from '../format.ts'
import { useExam } from '../queries.ts'

export function ExamDetailPage() {
  const { examId = '' } = useParams()
  const exam = useExam(examId)

  return (
    <>
      <Link to="/exams" className="inline-flex min-h-11 items-center text-sm text-indigo-600 hover:underline">
        ← All exams
      </Link>
      {exam.isPending ? (
        <Loading />
      ) : exam.isError ? (
        <ErrorMessage error={exam.error} />
      ) : (
        <ExamDetail exam={exam.data} />
      )}
    </>
  )
}

type View = 'tasks' | 'pages'

function ExamDetail({ exam }: { exam: Exam }) {
  const [view, setView] = useState<View>('tasks')
  const processed = exam.page_count !== null

  return (
    <>
      <div className="space-y-1">
        <div className="flex items-start justify-between gap-3">
          <PageTitle>
            <span className="font-mono text-lg text-indigo-700">{exam.subject_code}</span> {exam.label}
          </PageTitle>
          <StatusBadge status={exam.status} />
        </div>
        <p className="text-sm text-slate-500">Uploaded {formatDateTime(exam.uploaded_at)}</p>
      </div>

      {exam.status === 'processing' && <ProcessingProgress exam={exam} />}
      {exam.status === 'failed' && <FailedExam exam={exam} />}

      {processed && (
        <>
          <Toggle>
            <ToggleButton active={view === 'tasks'} onClick={() => setView('tasks')}>
              Tasks
            </ToggleButton>
            <ToggleButton active={view === 'pages'} onClick={() => setView('pages')}>
              Pages
            </ToggleButton>
          </Toggle>
          {view === 'tasks' ? (
            <ReviewPanel exam={exam} />
          ) : (
            // The pages are meant to be read; keep them at a readable width.
            <div className="mx-auto max-w-3xl">
              <Pages exam={exam} examPages={exam.page_count ?? 0} />
            </div>
          )}
        </>
      )}
    </>
  )
}

function Pages({ exam, examPages }: { exam: Exam; examPages: number }) {
  const [kind, setKind] = useState<PageKind>('exam')
  const solutionPages = exam.solution_page_count
  const count = kind === 'solution' && solutionPages !== null ? solutionPages : examPages

  return (
    <section className="space-y-4" aria-label="Pages">
      {solutionPages !== null && (
        <Toggle>
          <ToggleButton active={kind === 'exam'} onClick={() => setKind('exam')}>
            Exam ({examPages})
          </ToggleButton>
          <ToggleButton active={kind === 'solution'} onClick={() => setKind('solution')}>
            Solution ({solutionPages})
          </ToggleButton>
        </Toggle>
      )}
      <ol className="space-y-4">
        {Array.from({ length: count }, (_, index) => index + 1).map((number) => (
          <li key={`${kind}-${number}`}>
            <figure>
              <figcaption className="mb-1 text-xs text-slate-500">
                Page {number} of {count}
              </figcaption>
              {/* The size is that of an A4 page at 150 DPI; it only reserves room until the image loads. */}
              <img
                src={pageImageUrl(exam.id, kind, number)}
                alt={`${kind === 'exam' ? 'Exam' : 'Solution'} page ${number}`}
                width={1240}
                height={1754}
                loading="lazy"
                className="h-auto w-full rounded-lg border border-slate-200 bg-white shadow-xs"
              />
            </figure>
          </li>
        ))}
      </ol>
    </section>
  )
}

function Toggle({ children }: { children: ReactNode }) {
  return (
    <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5" role="group">
      {children}
    </div>
  )
}

function ToggleButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`min-h-10 rounded-md px-4 text-sm font-medium transition-colors ${
        active ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100'
      }`}
    >
      {children}
    </button>
  )
}
