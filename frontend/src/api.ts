// Typed client for the backend's JSON API. The session lives in an HTTP-only
// cookie, so there is no token handling here.

export type Subject = {
  code: string
  name: string
  exam_date: string | null // YYYY-MM-DD
}

export type ExamStatus = 'processing' | 'needs_review' | 'ready' | 'failed'

export type Progress = {
  stage: string
  done: number
  total: number
}

export type Exam = {
  id: string
  subject_code: string
  label: string
  status: ExamStatus
  error: string | null
  has_solution: boolean
  page_count: number | null
  solution_page_count: number | null
  uploaded_at: string
  progress: Progress | null
}

export type PageKind = 'exam' | 'solution'

export type Topic = {
  id: string
  name: string
}

/** A rectangle on a page; the edges are fractions of the page's width and height. */
export type Region = {
  page: number
  top: number
  bottom: number
  left: number
  right: number
}

export type Task = {
  id: string
  exam_id: string
  parent_id: string | null
  number: string
  title: string | null
  position: number
  points: number | null
  /** The task's own topics. A sub-task without any takes its parent's. */
  topics: Topic[]
  /** Where on the exam's pages the task is; one image per region, in the same order. */
  regions: Region[]
  images: string[]
  solution_images: string[]
  solution_text: string | null
}

export type ExamTasks = {
  tasks: Task[]
  topics: Topic[]
}

/** Fields left out are not changed. */
export type TaskChanges = {
  number?: string
  title?: string | null
  points?: number | null
  topics?: string[]
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, { credentials: 'same-origin', ...init })
  } catch {
    throw new ApiError(0, 'Could not reach the server.')
  }
  if (response.status === 204) return undefined as T

  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(response.status, describeError(body) ?? `Request failed (${response.status}).`)
  }
  return body as T
}

// Our own errors carry a string in `detail`; request-validation errors carry a list.
function describeError(body: unknown): string | null {
  if (typeof body !== 'object' || body === null || !('detail' in body)) return null
  const { detail } = body
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item: unknown) =>
        typeof item === 'object' && item !== null && 'msg' in item && typeof item.msg === 'string'
          ? item.msg
          : null,
      )
      .filter((message) => message !== null)
    if (messages.length > 0) return messages.join('; ')
  }
  return null
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export type SubjectInput = { code: string; name: string; exam_date: string | null }

export type ExamUpload = {
  subjectCode: string
  label: string
  pdf: File
  solutionPdf: File | null
}

export const api = {
  session: () => request<{ authenticated: boolean }>('/auth/session'),
  login: (password: string) => request<void>('/auth/login', json('POST', { password })),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),

  subjects: () => request<Subject[]>('/subjects'),
  createSubject: (subject: SubjectInput) => request<Subject>('/subjects', json('POST', subject)),
  updateSubject: ({ code, name, exam_date }: SubjectInput) =>
    request<Subject>(`/subjects/${encodeURIComponent(code)}`, json('PUT', { name, exam_date })),
  deleteSubject: (code: string) =>
    request<void>(`/subjects/${encodeURIComponent(code)}`, { method: 'DELETE' }),

  exams: () => request<Exam[]>('/exams'),
  exam: (id: string) => request<Exam>(`/exams/${id}`),
  uploadExam: ({ subjectCode, label, pdf, solutionPdf }: ExamUpload) => {
    const form = new FormData()
    form.set('subject_code', subjectCode)
    form.set('label', label)
    form.set('pdf', pdf)
    if (solutionPdf) form.set('solution_pdf', solutionPdf)
    return request<Exam>('/exams', { method: 'POST', body: form })
  },
  retryExam: (id: string) => request<Exam>(`/exams/${id}/retry`, { method: 'POST' }),

  examTasks: (examId: string) => request<ExamTasks>(`/exams/${examId}/tasks`),
  approveExam: (examId: string) => request<Exam>(`/exams/${examId}/approve`, { method: 'POST' }),
  updateTask: (taskId: string, changes: TaskChanges) =>
    request<void>(`/tasks/${taskId}`, json('PATCH', changes)),
  deleteTask: (taskId: string) => request<void>(`/tasks/${taskId}`, { method: 'DELETE' }),
  mergeTaskWithPrevious: (taskId: string) =>
    request<void>(`/tasks/${taskId}/merge-previous`, { method: 'POST' }),
  renameTopic: (topicId: string, name: string) =>
    request<Topic>(`/topics/${topicId}`, json('PATCH', { name })),
  splitTask: (taskId: string, imageIndex: number, fraction: number) =>
    request<void>(`/tasks/${taskId}/split`, json('POST', { image_index: imageIndex, fraction })),
}

export function pageImageUrl(examId: string, kind: PageKind, number: number): string {
  return `/api/exams/${examId}/pages/${kind}/${number}`
}
