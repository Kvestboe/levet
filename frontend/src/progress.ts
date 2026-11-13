// How a topic's weakness (0-1) is put into words and colours.

export type WeaknessLevel = { label: string; fill: string; track: string }

// The fill carries the state and the track is a lighter step of the same hue,
// so the state reads across the whole bar. The word says it again: the colour
// is never the only signal.
export function weaknessLevel(weakness: number): WeaknessLevel {
  if (weakness >= 0.999) return { label: 'Not practised yet', fill: 'bg-red-500', track: 'bg-red-100' }
  if (weakness >= 0.66) return { label: 'Weak', fill: 'bg-red-500', track: 'bg-red-100' }
  if (weakness >= 0.33) return { label: 'Getting there', fill: 'bg-amber-500', track: 'bg-amber-100' }
  return { label: 'Strong', fill: 'bg-emerald-500', track: 'bg-emerald-100' }
}

export const percent = (value: number) => `${Math.round(value * 100)}%`
