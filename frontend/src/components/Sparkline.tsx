interface Props { values: number[]; width?: number; height?: number; colour?: string }

/** Health trend. Deliberately unlabelled and small — it is a glance, not a chart. */
export function Sparkline({ values, width = 88, height = 22, colour = 'var(--color-transit)' }: Props) {
  if (values.length < 2) return <svg width={width} height={height} aria-hidden />
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const span = hi - lo || 1
  const d = values
    .map((v, i) => `${i ? 'L' : 'M'}${((i / (values.length - 1)) * width).toFixed(1)},${(height - ((v - lo) / span) * height).toFixed(1)}`)
    .join('')
  return (
    <svg width={width} height={height} aria-hidden className="overflow-visible">
      <path d={d} fill="none" stroke={colour} strokeWidth="1.3" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
