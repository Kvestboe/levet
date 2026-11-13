// Grades, timing and small helpers shared by the practice modes.

import { useEffect, useRef, useState } from 'react'
import type { Grade } from './api.ts'

export const GRADES: { grade: Grade; label: string; hint: string; className: string }[] = [
  {
    grade: 'again',
    label: 'Again',
    hint: 'Could not do it',
    className: 'border-red-300 bg-red-50 text-red-800 hover:bg-red-100',
  },
  {
    grade: 'hard',
    label: 'Hard',
    hint: 'Got there, with trouble',
    className: 'border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100',
  },
  {
    grade: 'good',
    label: 'Good',
    hint: 'Solved it',
    className: 'border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100',
  },
  {
    grade: 'easy',
    label: 'Easy',
    hint: 'Solved it at once',
    className: 'border-sky-300 bg-sky-50 text-sky-800 hover:bg-sky-100',
  },
]

const GRADE_SCORES: Record<Grade, number> = { again: 0, hard: 0.4, good: 0.8, easy: 1 }

export function gradeScore(grade: Grade): number {
  return GRADE_SCORES[grade]
}

export function gradeLabel(grade: Grade): string {
  return GRADES.find((option) => option.grade === grade)?.label ?? grade
}

/**
 * Seconds spent since `resetKey` last changed. Time only counts while the page
 * is visible, so leaving the tab open over lunch does not count as an hour.
 */
export function useStopwatch(resetKey: string, running = true): number {
  const [seconds, setSeconds] = useState(0)
  const elapsed = useRef(0)
  // Pausing must not restart the count, so `running` is read through a ref
  // instead of being a dependency of the effect that owns the timer.
  const isRunning = useRef(running)
  useEffect(() => {
    isRunning.current = running
  }, [running])

  useEffect(() => {
    elapsed.current = 0
    let last = Date.now()
    const tick = () => {
      const now = Date.now()
      if (isRunning.current && document.visibilityState === 'visible') elapsed.current += now - last
      last = now
      setSeconds(Math.floor(elapsed.current / 1000))
    }
    tick()
    const timer = window.setInterval(tick, 1000)
    document.addEventListener('visibilitychange', tick)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', tick)
    }
  }, [resetKey])

  return seconds
}

export function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = String(seconds % 60).padStart(2, '0')
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, '0')}:${rest}` : `${minutes}:${rest}`
}

/** "in 10 minutes", "in 3 days": when a task is due again. */
export function describeDue(dueIso: string, now: Date = new Date()): string {
  const seconds = (new Date(dueIso).getTime() - now.getTime()) / 1000
  if (seconds < 90) return 'in about a minute'
  if (seconds < 3600) return `in ${Math.round(seconds / 60)} minutes`
  if (seconds < 36 * 3600) return `in ${Math.round(seconds / 3600)} hours`
  return `in ${Math.round(seconds / 86_400)} days`
}

/** Whether a key press belongs to a text field and must not act as a shortcut. */
export function isTyping(event: KeyboardEvent): boolean {
  const target = event.target
  return (
    target instanceof HTMLElement &&
    (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
  )
}
