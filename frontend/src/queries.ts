import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './api.ts'
import type { Exam } from './api.ts'

export const keys = {
  session: ['session'] as const,
  subjects: ['subjects'] as const,
  exams: ['exams'] as const,
  exam: (id: string) => ['exams', id] as const,
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
