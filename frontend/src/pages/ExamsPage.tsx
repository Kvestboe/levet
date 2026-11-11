import { useRef, useState } from 'react'
import { Link } from 'react-router'
import type { Exam, Subject } from '../api.ts'
import { FailedExam } from '../components/FailedExam.tsx'
import {
  Button,
  Card,
  ErrorMessage,
  Field,
  Loading,
  PageTitle,
  ProcessingProgress,
  StatusBadge,
  fileInputClass,
  inputClass,
} from '../components/ui.tsx'
import { formatDateTime } from '../format.ts'
import { useExams, useSubjects, useUploadExam } from '../queries.ts'

export function ExamsPage() {
  const subjects = useSubjects()
  const exams = useExams()
  return (
    <>
      <PageTitle>Exams</PageTitle>
      {subjects.isPending ? (
        <Loading />
      ) : subjects.isError ? (
        <ErrorMessage error={subjects.error} />
      ) : subjects.data.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-600">
            An exam belongs to a subject.{' '}
            <Link to="/subjects" className="font-medium text-indigo-600 hover:underline">
              Add a subject
            </Link>{' '}
            first, then upload its exams here.
          </p>
        </Card>
      ) : (
        <UploadExam subjects={subjects.data} />
      )}

      {exams.isPending ? (
        <Loading />
      ) : exams.isError ? (
        <ErrorMessage error={exams.error} />
      ) : exams.data.length === 0 ? (
        <p className="text-sm text-slate-500">No exams uploaded yet.</p>
      ) : (
        <ul className="space-y-3">
          {exams.data.map((exam) => (
            <li key={exam.id}>
              <ExamCard exam={exam} />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function UploadExam({ subjects }: { subjects: Subject[] }) {
  const upload = useUploadExam()
  const [subjectCode, setSubjectCode] = useState(subjects[0].code)
  const [label, setLabel] = useState('')
  const pdfInput = useRef<HTMLInputElement>(null)
  const solutionInput = useRef<HTMLInputElement>(null)

  return (
    <Card>
      <h2 className="mb-3 text-base font-semibold">Upload exam</h2>
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          const pdf = pdfInput.current?.files?.[0]
          if (!pdf) return
          upload.mutate(
            {
              subjectCode,
              label: label.trim(),
              pdf,
              solutionPdf: solutionInput.current?.files?.[0] ?? null,
            },
            {
              onSuccess: () => {
                setLabel('')
                if (pdfInput.current) pdfInput.current.value = ''
                if (solutionInput.current) solutionInput.current.value = ''
              },
            },
          )
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Subject">
            <select
              required
              value={subjectCode}
              onChange={(event) => setSubjectCode(event.target.value)}
              className={inputClass}
            >
              {subjects.map((subject) => (
                <option key={subject.code} value={subject.code}>
                  {subject.code} · {subject.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Label">
            <input
              required
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="Høst 2023"
              autoComplete="off"
              maxLength={200}
              className={inputClass}
            />
          </Field>
        </div>
        <Field label="Exam PDF">
          <input ref={pdfInput} type="file" accept="application/pdf,.pdf" required className={fileInputClass} />
        </Field>
        <Field label="Solution PDF" hint="(optional)">
          <input ref={solutionInput} type="file" accept="application/pdf,.pdf" className={fileInputClass} />
        </Field>
        <ErrorMessage error={upload.error} />
        <Button type="submit" disabled={upload.isPending}>
          {upload.isPending ? 'Uploading…' : 'Upload'}
        </Button>
      </form>
    </Card>
  )
}

function ExamCard({ exam }: { exam: Exam }) {
  return (
    <Card className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to={`/exams/${exam.id}`} className="text-base font-medium break-words hover:underline">
            <span className="font-mono text-sm font-semibold text-indigo-700">{exam.subject_code}</span>{' '}
            {exam.label}
          </Link>
          <p className="mt-0.5 text-sm text-slate-500">
            Uploaded {formatDateTime(exam.uploaded_at)}
            {exam.page_count !== null && ` · ${describePages(exam)}`}
          </p>
        </div>
        <StatusBadge status={exam.status} />
      </div>
      {exam.status === 'processing' && <ProcessingProgress exam={exam} />}
      {exam.status === 'failed' && <FailedExam exam={exam} />}
    </Card>
  )
}

function describePages(exam: Exam): string {
  const pages = `${exam.page_count} ${exam.page_count === 1 ? 'page' : 'pages'}`
  return exam.solution_page_count === null ? pages : `${pages} + ${exam.solution_page_count} solution`
}
