import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { ApiError } from './api.ts'
import App from './App.tsx'
import './index.css'
import { keys } from './queries.ts'

// Any 401 means the session is gone (expired, or the password was changed):
// flip the session flag and the app falls back to the login page.
function handleError(error: Error) {
  if (error instanceof ApiError && error.status === 401) {
    queryClient.setQueryData(keys.session, { authenticated: false })
  }
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: handleError }),
  mutationCache: new MutationCache({ onError: handleError }),
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      // Retry network trouble and server errors, never a 4xx: it will not change.
      retry: (failures, error) =>
        failures < 2 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
