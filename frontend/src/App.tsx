import { Link, Route, Routes } from 'react-router'
import { Layout } from './components/Layout.tsx'
import { Button, ErrorMessage, Loading, PageTitle } from './components/ui.tsx'
import { DashboardPage } from './pages/DashboardPage.tsx'
import { ExamDetailPage } from './pages/ExamDetailPage.tsx'
import { ExamsPage } from './pages/ExamsPage.tsx'
import { LoginPage } from './pages/LoginPage.tsx'
import { MockExamPage } from './pages/MockExamPage.tsx'
import {
  MockExamList,
  PracticePage,
  PractiseNow,
  TopicList,
  TopicSession,
} from './pages/PracticePage.tsx'
import { SettingsPage } from './pages/SettingsPage.tsx'
import { SubjectsPage } from './pages/SubjectsPage.tsx'
import { TopicDetailPage } from './pages/TopicDetailPage.tsx'
import { useSession } from './queries.ts'

export default function App() {
  const session = useSession()

  if (session.isPending) return <Loading />
  if (session.isError) {
    return (
      <main className="mx-auto max-w-sm space-y-4 px-4 py-16">
        <ErrorMessage error={session.error} />
        <Button onClick={() => session.refetch()}>Try again</Button>
      </main>
    )
  }
  if (!session.data.authenticated) return <LoginPage />

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="practice" element={<PracticePage />}>
          <Route index element={<PractiseNow />} />
          <Route path="topics" element={<TopicList />} />
          <Route path="topics/:topicId" element={<TopicSession />} />
          <Route path="mock" element={<MockExamList />} />
          <Route path="mock/:examId" element={<MockExamPage />} />
        </Route>
        <Route path="exams" element={<ExamsPage />} />
        <Route path="exams/:examId" element={<ExamDetailPage />} />
        <Route path="subjects" element={<SubjectsPage />} />
        <Route path="topics/:topicId" element={<TopicDetailPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

function NotFound() {
  return (
    <>
      <PageTitle>Page not found</PageTitle>
      <Link to="/" className="text-indigo-600 hover:underline">
        Go to the dashboard
      </Link>
    </>
  )
}
