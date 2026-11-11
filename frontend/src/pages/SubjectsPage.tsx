import { useState } from 'react'
import type { Subject, SubjectInput } from '../api.ts'
import { Button, Card, ErrorMessage, Field, Loading, PageTitle, inputClass } from '../components/ui.tsx'
import { daysUntil, describeCountdown, formatDate } from '../format.ts'
import { useCreateSubject, useDeleteSubject, useSubjects, useUpdateSubject } from '../queries.ts'

export function SubjectsPage() {
  const subjects = useSubjects()
  return (
    <>
      <PageTitle>Subjects</PageTitle>
      <AddSubject />
      {subjects.isPending ? (
        <Loading />
      ) : subjects.isError ? (
        <ErrorMessage error={subjects.error} />
      ) : subjects.data.length === 0 ? (
        <p className="text-sm text-slate-500">No subjects yet. Add the first one above.</p>
      ) : (
        <ul className="space-y-3">
          {subjects.data.map((subject) => (
            <li key={subject.code}>
              <SubjectCard subject={subject} />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function AddSubject() {
  const create = useCreateSubject()
  // Changing the key remounts the form, which clears it after a successful save.
  const [formKey, setFormKey] = useState(0)
  return (
    <Card>
      <h2 className="mb-3 text-base font-semibold">Add subject</h2>
      <SubjectForm
        key={formKey}
        submitLabel="Add subject"
        pending={create.isPending}
        error={create.error}
        onSubmit={(input) => create.mutate(input, { onSuccess: () => setFormKey((key) => key + 1) })}
      />
    </Card>
  )
}

function SubjectCard({ subject }: { subject: Subject }) {
  const [editing, setEditing] = useState(false)
  const update = useUpdateSubject()
  const remove = useDeleteSubject()

  if (editing) {
    return (
      <Card>
        <SubjectForm
          initial={subject}
          submitLabel="Save"
          pending={update.isPending}
          error={update.error}
          onSubmit={(input) => update.mutate(input, { onSuccess: () => setEditing(false) })}
          onCancel={() => {
            update.reset()
            setEditing(false)
          }}
        />
      </Card>
    )
  }

  const days = subject.exam_date === null ? null : daysUntil(subject.exam_date)
  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <p className="font-mono text-sm font-semibold text-indigo-700">{subject.code}</p>
          <p className="text-base font-medium break-words">{subject.name}</p>
          <p className="mt-1 text-sm text-slate-500">
            {subject.exam_date === null || days === null
              ? 'No exam date set'
              : `${formatDate(subject.exam_date)} · ${describeCountdown(days)}`}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setEditing(true)}>
            Edit
          </Button>
          <Button
            variant="danger"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Delete ${subject.code}?`)) remove.mutate(subject.code)
            }}
          >
            Delete
          </Button>
        </div>
      </div>
      <ErrorMessage error={remove.error} />
    </Card>
  )
}

type SubjectFormProps = {
  /** Present when editing: the code is the subject's identity and cannot change. */
  initial?: Subject
  submitLabel: string
  pending: boolean
  error: Error | null
  onSubmit: (input: SubjectInput) => void
  onCancel?: () => void
}

function SubjectForm({ initial, submitLabel, pending, error, onSubmit, onCancel }: SubjectFormProps) {
  const [code, setCode] = useState(initial?.code ?? '')
  const [name, setName] = useState(initial?.name ?? '')
  const [examDate, setExamDate] = useState(initial?.exam_date ?? '')

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit({ code: code.trim(), name: name.trim(), exam_date: examDate || null })
      }}
    >
      <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
        <Field label="Course code">
          <input
            required
            disabled={initial !== undefined}
            value={code}
            onChange={(event) => setCode(event.target.value.toUpperCase())}
            placeholder="IDATT2202"
            autoCapitalize="characters"
            autoComplete="off"
            maxLength={32}
            className={`${inputClass} font-mono disabled:bg-slate-100 disabled:text-slate-500`}
          />
        </Field>
        <Field label="Name">
          <input
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Operativsystemer"
            autoComplete="off"
            maxLength={200}
            className={inputClass}
          />
        </Field>
      </div>
      <Field label="Exam date" hint="(optional)">
        <input
          type="date"
          value={examDate}
          onChange={(event) => setExamDate(event.target.value)}
          className={`${inputClass} sm:w-auto`}
        />
      </Field>
      <ErrorMessage error={error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={pending}>
          {pending ? 'Saving…' : submitLabel}
        </Button>
        {onCancel && (
          <Button variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  )
}
