import { useState } from 'react'
import type { AppSettings, Language } from '../api.ts'
import { Button, Card, ErrorMessage, Field, Loading, PageTitle, inputClass } from '../components/ui.tsx'
import { percent } from '../progress.ts'
import { useLogout, useSettings, useUpdateSettings } from '../queries.ts'

const DEFAULT_WEIGHTS = { mastery_weight: 0.6, staleness_weight: 0.25, coverage_weight: 0.15 }

const languages: { value: Language; label: string }[] = [
  { value: 'nb', label: 'Bokmål' },
  { value: 'nn', label: 'Nynorsk' },
  { value: 'en', label: 'English' },
]

export function SettingsPage() {
  const settings = useSettings()
  const logout = useLogout()
  return (
    <>
      <PageTitle>Settings</PageTitle>
      {settings.isPending ? (
        <Loading />
      ) : settings.isError ? (
        <ErrorMessage error={settings.error} />
      ) : (
        <>
          <WeightsForm settings={settings.data} />
          <LanguageForm settings={settings.data} />
        </>
      )}

      <Card>
        <h2 className="text-base font-semibold">Task extraction</h2>
        <p className="mt-1 text-sm text-slate-600">
          Tasks are found on this server from the PDF itself. No API key or outside service is used.
        </p>
      </Card>

      <Card>
        <h2 className="mb-3 text-base font-semibold">Session</h2>
        <Button variant="secondary" disabled={logout.isPending} onClick={() => logout.mutate()}>
          Log out
        </Button>
      </Card>
    </>
  )
}

const weightFields = [
  {
    name: 'mastery_weight',
    label: 'Mastery',
    hint: 'how badly the topic’s tasks went',
  },
  {
    name: 'staleness_weight',
    label: 'Staleness',
    hint: 'how long since the topic was practised',
  },
  {
    name: 'coverage_weight',
    label: 'Coverage',
    hint: 'how much of the topic is still untried',
  },
] as const

type Weights = typeof DEFAULT_WEIGHTS

const asText = (weights: Weights) => ({
  mastery_weight: String(weights.mastery_weight),
  staleness_weight: String(weights.staleness_weight),
  coverage_weight: String(weights.coverage_weight),
})

function WeightsForm({ settings }: { settings: AppSettings }) {
  const update = useUpdateSettings()
  const [values, setValues] = useState(() => asText(settings))

  const numbers = weightFields.map(({ name }) => Number(values[name].replace(',', '.')))
  const total = numbers.reduce((sum, value) => sum + value, 0)
  const valid = numbers.every((value) => Number.isFinite(value) && value >= 0) && total > 0
  // After saving, the fields show what the server now holds.
  const save = (weights: Weights) => update.mutate(weights, { onSuccess: (saved) => setValues(asText(saved)) })

  return (
    <Card>
      <h2 className="text-base font-semibold">Weakness weights</h2>
      <p className="mt-1 text-sm text-slate-600">
        A topic’s weakness is a blend of three things. Only their proportions matter.
      </p>
      <form
        className="mt-3 space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          if (!valid) return
          save({ mastery_weight: numbers[0], staleness_weight: numbers[1], coverage_weight: numbers[2] })
        }}
      >
        <div className="grid gap-3 sm:grid-cols-3">
          {weightFields.map(({ name, label, hint }, index) => (
            <div key={name}>
              <Field label={label}>
                <input
                  inputMode="decimal"
                  value={values[name]}
                  onChange={(event) => {
                    update.reset() // what is on screen is no longer what was saved
                    setValues((current) => ({ ...current, [name]: event.target.value }))
                  }}
                  className={inputClass}
                />
              </Field>
              <p className="mt-1 text-xs text-slate-500">
                {valid ? `${percent(numbers[index] / total)} · ` : ''}
                {hint}
              </p>
            </div>
          ))}
        </div>
        {!valid && (
          <p role="alert" className="text-sm text-red-700">
            Weights must be numbers, none below zero and not all zero.
          </p>
        )}
        <ErrorMessage error={update.error} />
        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" disabled={!valid || update.isPending}>
            {update.isPending ? 'Saving…' : 'Save weights'}
          </Button>
          <Button variant="secondary" disabled={update.isPending} onClick={() => save(DEFAULT_WEIGHTS)}>
            Reset to defaults
          </Button>
          {update.isSuccess && <span className="text-sm text-emerald-700">Saved</span>}
        </div>
      </form>
    </Card>
  )
}

function LanguageForm({ settings }: { settings: AppSettings }) {
  const update = useUpdateSettings()
  return (
    <Card>
      <h2 className="text-base font-semibold">Exam language</h2>
      <p className="mt-1 text-sm text-slate-600">
        When an exam prints every task in several languages, this is the version that is kept. English is used if
        the exam does not have it. Applies to exams uploaded from now on.
      </p>
      <div className="mt-3 max-w-xs">
        <Field label="Preferred language">
          <select
            value={settings.preferred_language}
            disabled={update.isPending}
            onChange={(event) => update.mutate({ preferred_language: event.target.value as Language })}
            className={inputClass}
          >
            {languages.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="mt-2">
        <ErrorMessage error={update.error} />
      </div>
    </Card>
  )
}
