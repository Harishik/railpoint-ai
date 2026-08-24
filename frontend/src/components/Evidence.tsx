import type { Attribution } from '../lib/types'
import { num } from '../lib/format'

interface Props {
  attributions: Attribution[]
  onHover: (feature: string | null) => void
}

/**
 * Local attribution. Bars diverge from a centre line so the direction of
 * evidence is readable at a glance — pushing toward the diagnosis, or against
 * it — and hovering one lights the waveform phase it came from.
 */
export function Evidence({ attributions, onHover }: Props) {
  const max = Math.max(1e-6, ...attributions.map((a) => Math.abs(a.contribution)))
  if (!attributions.length) {
    return <p className="text-[12px] text-ink-faint">No attribution available for this event.</p>
  }
  return (
    <ul className="flex flex-col gap-1.5" onMouseLeave={() => onHover(null)}>
      {attributions.map((a) => {
        const frac = Math.abs(a.contribution) / max
        const pos = a.contribution >= 0
        return (
          <li
            key={a.feature}
            onMouseEnter={() => onHover(a.feature)}
            className="group grid grid-cols-[1fr_auto] items-center gap-2 rounded px-1 py-0.5 transition-colors duration-150 hover:bg-surface-2"
          >
            <div className="min-w-0">
              <div className="truncate text-[12px] text-ink-dim">{a.label}</div>
              <div className="relative mt-1 h-1.5 rounded-full bg-surface-3">
                <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
                <div
                  className="absolute inset-y-0 rounded-full transition-[width] duration-300"
                  style={{
                    width: `${(frac * 50).toFixed(1)}%`,
                    left: pos ? '50%' : undefined,
                    right: pos ? undefined : '50%',
                    background: pos ? 'var(--color-fault)' : 'var(--color-normal)',
                  }}
                />
              </div>
            </div>
            <span className="num text-[12px] tabular-nums text-ink-faint">{num(a.value)}</span>
          </li>
        )
      })}
    </ul>
  )
}
