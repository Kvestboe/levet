import type { Exam } from '../api.ts'
import { useRetryExam } from '../queries.ts'
import { Button, ErrorMessage } from './ui.tsx'

/** The error a failed exam ended with, and a button to send it through processing again. */
export function FailedExam({ exam }: { exam: Exam }) {
  const retry = useRetryExam()
  return (
    <div className="space-y-2">
      <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm break-words text-red-800">
        {exam.error}
      </p>
      <ErrorMessage error={retry.error} />
      <Button variant="secondary" disabled={retry.isPending} onClick={() => retry.mutate(exam.id)}>
        {retry.isPending ? 'Retrying…' : 'Retry'}
      </Button>
    </div>
  )
}
