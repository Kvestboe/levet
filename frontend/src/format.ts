const DAY_MS = 86_400_000

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

// A calendar date from the API ("2026-12-01") as local midnight. `new Date(iso)`
// would read it as UTC and can land on the previous day.
function parseDate(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

export function formatDate(iso: string): string {
  return dateFormat.format(parseDate(iso))
}

export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso))
}

/** Whole days from today until the given calendar date; negative once it has passed. */
export function daysUntil(iso: string, now: Date = new Date()): number {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  return Math.round((parseDate(iso).getTime() - today.getTime()) / DAY_MS)
}

export function describeCountdown(days: number): string {
  if (days < 0) return 'Exam has passed'
  if (days === 0) return 'Exam is today'
  if (days === 1) return 'Exam is tomorrow'
  return `${days} days to exam`
}
