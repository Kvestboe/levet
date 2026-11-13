import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, PointerEvent } from 'react'
import type { MasteryPoint } from '../api.ts'
import { formatDate } from '../format.ts'
import { percent } from '../progress.ts'

// Plot geometry, in CSS pixels. The right margin holds the end label.
const HEIGHT = 190
const MARGIN = { top: 14, right: 46, bottom: 24, left: 46 }
const TICKS = [0, 0.5, 1]

/**
 * Mastery day by day as a line over a light wash, 0-100%.
 *
 * One series, so no legend: the heading above says what is plotted. The last
 * value is labelled on the chart, the rest are read from the axis, by pointing
 * (a crosshair snaps to the nearest day), with the arrow keys, or from the
 * table underneath.
 */
export function MasteryChart({ history }: { history: MasteryPoint[] }) {
  const frame = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(640)
  const [active, setActive] = useState<number | null>(null)

  useEffect(() => {
    const element = frame.current
    if (!element) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  if (history.length === 0) {
    return <p className="text-sm text-slate-500">Nothing attempted in this topic yet.</p>
  }

  const plotWidth = Math.max(10, width - MARGIN.left - MARGIN.right)
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom
  const last = history.length - 1
  // A single day sits in the middle; otherwise days are spread edge to edge.
  const x = (index: number) => MARGIN.left + (last === 0 ? plotWidth / 2 : (index / last) * plotWidth)
  const y = (value: number) => MARGIN.top + (1 - value) * plotHeight
  const points = history.map((point, index) => `${x(index)},${y(point.mastery)}`)
  const baseline = y(0)

  const nearest = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect()
    const ratio = (event.clientX - box.left - MARGIN.left) / plotWidth
    return Math.min(last, Math.max(0, Math.round(ratio * last)))
  }
  const onKey = (event: KeyboardEvent<SVGSVGElement>) => {
    const step = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0
    if (step === 0) return
    event.preventDefault()
    setActive((current) => Math.min(last, Math.max(0, (current ?? last) + step)))
  }

  const shown = active === null ? null : history[active]
  const end = history[last]

  return (
    <div>
      <div ref={frame} className="relative">
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label={`Mastery over time, from ${formatDate(history[0].day)} to ${formatDate(end.day)}. Now ${percent(end.mastery)}. Use the arrow keys to read each day.`}
          tabIndex={0}
          className="block touch-pan-y rounded-lg outline-offset-2 focus-visible:outline-2 focus-visible:outline-indigo-600"
          onPointerMove={(event) => setActive(nearest(event))}
          onPointerDown={(event) => setActive(nearest(event))}
          onPointerLeave={() => setActive(null)}
          onFocus={() => setActive((current) => current ?? last)}
          onBlur={() => setActive(null)}
          onKeyDown={onKey}
        >
          {/* Recessive hairline grid with the axis values. */}
          {TICKS.map((tick) => (
            <g key={tick}>
              <line x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(tick)} y2={y(tick)} className="stroke-slate-200" />
              <text x={MARGIN.left - 8} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-slate-500 text-xs tabular-nums">
                {percent(tick)}
              </text>
            </g>
          ))}
          <text x={MARGIN.left} y={HEIGHT - 6} className="fill-slate-500 text-xs">
            {formatDate(history[0].day)}
          </text>
          {last > 0 && (
            <text x={MARGIN.left + plotWidth} y={HEIGHT - 6} textAnchor="end" className="fill-slate-500 text-xs">
              {formatDate(end.day)}
            </text>
          )}

          {last > 0 && (
            <>
              <polygon
                points={`${x(0)},${baseline} ${points.join(' ')} ${x(last)},${baseline}`}
                className="fill-indigo-600/10"
              />
              <polyline
                points={points.join(' ')}
                fill="none"
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
                className="stroke-indigo-600"
              />
            </>
          )}

          {/* The crosshair finds the day; nobody has to hit a 2px line. */}
          {shown && active !== null && (
            <line x1={x(active)} x2={x(active)} y1={MARGIN.top} y2={baseline} className="stroke-slate-400" />
          )}

          {/* End dot with a ring in the surface colour, and the one direct label. */}
          <circle cx={x(last)} cy={y(end.mastery)} r={5} className="fill-indigo-600 stroke-white" strokeWidth={2} />
          <text x={x(last) + 10} y={y(end.mastery)} dy="0.32em" className="fill-slate-900 text-sm font-semibold">
            {percent(end.mastery)}
          </text>
          {shown && active !== null && active !== last && (
            <circle cx={x(active)} cy={y(shown.mastery)} r={5} className="fill-indigo-600 stroke-white" strokeWidth={2} />
          )}
        </svg>

        {shown && active !== null && (
          <div
            role="status"
            className="pointer-events-none absolute top-0 -translate-x-1/2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-center shadow-sm"
            style={{ left: Math.min(width - 60, Math.max(60, x(active))) }}
          >
            <p className="flex items-center justify-center gap-1.5 text-sm font-semibold text-slate-900">
              <span className="inline-block h-0.5 w-3 rounded bg-indigo-600" aria-hidden="true" />
              {percent(shown.mastery)}
            </p>
            <p className="text-xs whitespace-nowrap text-slate-500">{formatDate(shown.day)}</p>
          </div>
        )}
      </div>

      <details className="mt-2">
        <summary className="min-h-10 cursor-pointer py-2 text-sm text-slate-600">Show as a table</summary>
        <table className="w-full max-w-xs text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
              <th scope="col" className="py-1.5 font-medium">Day</th>
              <th scope="col" className="py-1.5 text-right font-medium">Mastery</th>
            </tr>
          </thead>
          <tbody>
            {history.toReversed().map((point) => (
              <tr key={point.day} className="border-b border-slate-100">
                <td className="py-1.5">{formatDate(point.day)}</td>
                <td className="py-1.5 text-right tabular-nums">{percent(point.mastery)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}
