import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { Exam, ExamStatus } from '../api.ts'

type Variant = 'primary' | 'secondary' | 'danger'

const buttonVariants: Record<Variant, string> = {
  primary: 'bg-indigo-600 text-white hover:bg-indigo-500 active:bg-indigo-700',
  secondary: 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 active:bg-slate-100',
  danger: 'border border-red-200 bg-white text-red-700 hover:bg-red-50 active:bg-red-100',
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }

// min-h-11 is 44px: a comfortable tap target on a phone.
export function Button({ variant = 'primary', className = '', type = 'button', ...props }: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-50 ${buttonVariants[variant]} ${className}`}
      {...props}
    />
  )
}

// text-base keeps iOS from zooming in when a field gets focus.
export const inputClass =
  'block min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-2 focus:outline-indigo-500/30'

export const fileInputClass =
  'block w-full text-sm text-slate-600 file:mr-3 file:min-h-11 file:cursor-pointer file:rounded-lg file:border file:border-solid file:border-slate-300 file:bg-white file:px-4 file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-50'

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700">
        {label}
        {hint && <span className="ml-1 font-normal text-slate-500">{hint}</span>}
      </span>
      {children}
    </label>
  )
}

export function Card({ className = '', children }: { className?: string; children: ReactNode }) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white p-4 shadow-xs sm:p-5 ${className}`}>
      {children}
    </div>
  )
}

export function ErrorMessage({ error }: { error: Error | null | undefined }) {
  if (!error) return null
  return (
    <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      {error.message}
    </p>
  )
}

export function PageTitle({ children }: { children: ReactNode }) {
  return <h1 className="text-2xl font-semibold tracking-tight">{children}</h1>
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <p className="py-8 text-center text-sm text-slate-500">{label}</p>
}

const statusStyles: Record<ExamStatus, { label: string; className: string }> = {
  processing: { label: 'Processing', className: 'bg-amber-100 text-amber-800' },
  needs_review: { label: 'Needs review', className: 'bg-sky-100 text-sky-800' },
  ready: { label: 'Ready', className: 'bg-emerald-100 text-emerald-800' },
  failed: { label: 'Failed', className: 'bg-red-100 text-red-800' },
}

export function StatusBadge({ status }: { status: ExamStatus }) {
  const { label, className } = statusStyles[status]
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>
      {label}
    </span>
  )
}

const stageLabels: Record<string, string> = {
  rendering: 'Rendering pages',
  extracting: 'Finding tasks',
}

/** Progress of an exam that is being processed; "Queued" until the worker picks it up. */
export function ProcessingProgress({ exam }: { exam: Exam }) {
  const progress = exam.progress
  const percent = progress && progress.total > 0 ? (progress.done / progress.total) * 100 : 0
  const label = progress
    ? `${stageLabels[progress.stage] ?? progress.stage} · ${progress.done} of ${progress.total}`
    : 'Queued…'
  return (
    <div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(percent)}
        className="h-2 overflow-hidden rounded-full bg-slate-200"
      >
        <div
          className="h-full rounded-full bg-indigo-600 transition-[width] duration-300"
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="mt-1 text-xs text-slate-500">{label}</p>
    </div>
  )
}
