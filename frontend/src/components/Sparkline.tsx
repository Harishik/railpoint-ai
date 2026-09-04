interface Props {
  values: number[]
  width?: number
  height?: number
  colour?: string
  /** Marks the most recent reading, so a trend that has just turned is
   *  readable without counting pixels from the right edge. */
  tip?: boolean
  strokeWidth?: number
}

/** Health trend. Deliberately unlabelled and small — it is a glance, not a
 *  chart, and it is scaled to its own range so the *shape* is the message. */
export function Sparkline({ values, width = 120, height = 28, colour = 'var(--color-cyan)', tip = true, strokeWidth = 1.4 }: Props) {
  if (values.length < 2) return <svg width={width} height={height} aria-hidden />
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const span = hi - lo || 1
  const pad = 2
  const pts = values.map((v, i) => [
    (i / (values.length - 1)) * width,
    pad + (1 - (v - lo) / span) * (height - pad * 2),
  ] as const)
  const last = pts[pts.length - 1]

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden className="block overflow-visible">
      <polyline points={pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')}
        fill="none" stroke={colour} strokeWidth={strokeWidth} strokeLinejoin="round" strokeLinecap="round" />
      {tip && <circle cx={last[0].toFixed(1)} cy={last[1].toFixed(1)} r="2" fill={colour} />}
    </svg>
  )
}
