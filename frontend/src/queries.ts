import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api.ts'
import type { AppSettings, Exam, TaskChanges } from './api.ts'

export const keys = {
  session: ['session'] as const,
  subjects: ['subjects'] as const,
  exams: ['exams'] as const,
  exam: (id: string) => ['exams', id] as const,
  examTasks: (id: string) => ['exams', id, 'tasks'] as const,
  practice: ['practice'] as const,
  practiceQueue: (topicId?: string) => ['practice', 'queue', topicId ?? 'all'] as const,
  practiceTopics: ['practice', 'topics'] as const,
  mockExam: (examId: string) => ['practice', 'exam', examId] as const,
  dashboard: ['dashboard'] as const,
  topicDetail: (topicId: string) => ['topics', topicId] as const,
  settings: ['settings'] as const,
}

// How often to ask for news while an exam is being processed.
const POLL_MS = 1000

// --- session ---------------------------------------------------------------

export function useSession() {
  return useQuery({ queryKey: keys.session, queryFn: api.session, staleTime: Infinity })
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.login,
    onSuccess: () => queryClient.setQueryData(keys.session, { authenticated: true }),
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.setQueryData(keys.session, { authenticated: false })
      // Drop everything that was fetched under the old session. The session
      // query itself must stay: the app is subscribed to it to show the login page.
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== keys.session[0] })
    },
  })
}

// --- subjects --------------------------------------------------------------

export function useSubjects() {
  return useQuery({ queryKey: keys.subjects, queryFn: api.subjects })
}

function useSubjectMutation<TInput>(mutationFn: (input: TInput) => Promise<unknown>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.subjects }),
  })
}

export const useCreateSubject = () => useSubjectMutation(api.createSubject)
export const useUpdateSubject = () => useSubjectMutation(api.updateSubject)
export const useDeleteSubject = () => useSubjectMutation(api.deleteSubject)

// --- exams -----------------------------------------------------------------

export function useExams() {
  return useQuery({
    queryKey: keys.exams,
    queryFn: api.exams,
    refetchInterval: (query) =>
      query.state.data?.some((exam) => exam.status === 'processing') ? POLL_MS : false,
  })
}

export function useExam(id: string) {
  return useQuery({
    queryKey: keys.exam(id),
    queryFn: () => api.exam(id),
    refetchInterval: (query) => (query.state.data?.status === 'processing' ? POLL_MS : false),
  })
}

function useExamMutation<TInput>(mutationFn: (input: TInput) => Promise<Exam>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (exam) => {
      queryClient.setQueryData(keys.exam(exam.id), exam)
      return queryClient.invalidateQueries({ queryKey: keys.exams })
    },
  })
}

export const useUploadExam = () => useExamMutation(api.uploadExam)
export const useRetryExam = () => useExamMutation(api.retryExam)

// --- tasks and review ------------------------------------------------------

/** The exam's tasks. Not fetched while the exam is still being processed. */
export function useExamTasks(exam: Exam) {
  return useQuery({
    queryKey: keys.examTasks(exam.id),
    queryFn: () => api.examTasks(exam.id),
    enabled: exam.status === 'needs_review' || exam.status === 'ready',
  })
}

/** A change to one of an exam's tasks; the task list is fetched again afterwards. */
function useTaskMutation<TInput>(examId: string, mutationFn: (input: TInput) => Promise<void>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSettled: () => queryClient.invalidateQueries({ queryKey: keys.examTasks(examId) }),
  })
}

export const useUpdateTask = (examId: string) =>
  useTaskMutation(examId, ({ taskId, changes }: { taskId: string; changes: TaskChanges }) =>
    api.updateTask(taskId, changes),
  )

export const useDeleteTask = (examId: string) => useTaskMutation(examId, api.deleteTask)

export const useMergeTask = (examId: string) => useTaskMutation(examId, api.mergeTaskWithPrevious)

export const useSplitTask = (examId: string) =>
  useTaskMutation(
    examId,
    ({ taskId, imageIndex, fraction }: { taskId: string; imageIndex: number; fraction: number }) =>
      api.splitTask(taskId, imageIndex, fraction),
  )

/** Renames a topic on every task; renaming it to another topic's name merges the two. */
export function useRenameTopic() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ topicId, name }: { topicId: string; name: string }) =>
      api.renameTopic(topicId, name),
    // A topic belongs to the subject, so every exam's task list may show it.
    onSettled: () => queryClient.invalidateQueries({ queryKey: keys.exams }),
  })
}

export function useApproveExam() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.approveExam,
    onSuccess: (exam) => {
      queryClient.setQueryData(keys.exam(exam.id), exam)
      return queryClient.invalidateQueries({ queryKey: keys.exams })
    },
  })
}

// --- practice ---------------------------------------------------------------

/** What to practise now, best first; only one topic's tasks if `topicId` is given. */
export function usePracticeQueue(topicId?: string) {
  return useQuery({
    queryKey: keys.practiceQueue(topicId),
    queryFn: () => api.practiceQueue(topicId),
    // The order depends on the clock (tasks fall due), so never serve it from cache.
    staleTime: 0,
    gcTime: 0,
  })
}

export function usePracticeTopics() {
  return useQuery({ queryKey: keys.practiceTopics, queryFn: api.practiceTopics, staleTime: 0 })
}

/** The tasks of a mock exam. Fetched once: the set must not change under the user. */
export function useMockExamTasks(examId: string) {
  return useQuery({
    queryKey: keys.mockExam(examId),
    queryFn: () => api.mockExamTasks(examId),
    staleTime: Infinity,
  })
}

/** Logs an attempt. The caller decides when to ask for the queue again. */
export function useRecordAttempt() {
  return useMutation({ mutationFn: api.recordAttempt })
}

// --- dashboard, topic detail and settings ----------------------------------

// These follow the practice history and the clock, so they are always fetched afresh.

export function useDashboard() {
  return useQuery({ queryKey: keys.dashboard, queryFn: api.dashboard, staleTime: 0 })
}

export function useTopicDetail(topicId: string) {
  return useQuery({
    queryKey: keys.topicDetail(topicId),
    queryFn: () => api.topicDetail(topicId),
    staleTime: 0,
  })
}

export function useSettings() {
  return useQuery({ queryKey: keys.settings, queryFn: api.settings })
}

export function useUpdateSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (changes: Partial<AppSettings>) => api.updateSettings(changes),
    onSuccess: (settings) => queryClient.setQueryData(keys.settings, settings),
  })
}
