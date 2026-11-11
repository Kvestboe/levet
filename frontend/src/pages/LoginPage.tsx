import { useState } from 'react'
import { Button, ErrorMessage, Field, inputClass } from '../components/ui.tsx'
import { useLogin } from '../queries.ts'

export function LoginPage() {
  const login = useLogin()
  const [password, setPassword] = useState('')

  return (
    <main className="flex min-h-dvh items-center justify-center px-4">
      <form
        className="w-full max-w-sm space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          login.mutate(password)
        }}
      >
        <h1 className="text-3xl font-semibold tracking-tight text-indigo-600">levet</h1>
        <Field label="Password">
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            autoFocus
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className={inputClass}
          />
        </Field>
        <ErrorMessage error={login.error} />
        <Button type="submit" disabled={login.isPending} className="w-full">
          {login.isPending ? 'Logging in…' : 'Log in'}
        </Button>
      </form>
    </main>
  )
}
