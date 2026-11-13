// Figures shared by the dashboard, the topic list and the topic page.

import type { ReactNode } from 'react'
import { weaknessLevel } from '../progress.ts'

/** How weak a topic is, as a bar from 0 to 100%. */
export function WeaknessMeter({ name, weakness }: { name: string; weakness: number }) {
  const level = weaknessLevel(weakness)
  return (
    <div
      className={`h-2 overflow-hidden rounded-full ${level.track}`}
      role="meter"
      aria-label={`Weakness of ${name}`}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(weakness * 100)}
      aria-valuetext={`${Math.round(weakness * 100)}%, ${level.label.toLowerCase()}`}
    >
      <div className={`h-full rounded-full ${level.fill}`} style={{ width: `${Math.max(2, weakness * 100)}%` }} />
    </div>
  )
}

type StatTileProps = {
  label: string
  value: ReactNode
  /** A line of context under the value. */
  detail?: ReactNode
}

/** One headline number with its name. */
export function StatTile({ label, value, detail }: StatTileProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">{value}</p>
      {detail && <div className="mt-1 text-xs text-slate-500">{detail}</div>}
    </div>
  )
}
