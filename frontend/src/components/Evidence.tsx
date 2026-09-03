import type { Attribution } from '../lib/types'
import { num } from '../lib/format'

interface Props {
  attributions: Attribution[]
  onHover: (feature: string | null) => void
}

/**
 * Local attribution.
 *
 * Bars diverge from a centre line so the *direction* of evidence is readable at
 * a glance — supporting the diagnosis, or arguing against it — and hovering one
 * lights the waveform phase it came from.
 *
 * The measured value and the contribution are shown as separate columns on
 * purpose. Previously the bar length encoded contribution while the only number
 * on the row was the measured value, so a long bar sat beside "170.00" and read
 * as if the bar meant 170. Two quantities in one row with one label is how a
 * chart misleads without ever being wrong.
 */
export function Evidence({ attributions, onHover }: Props) {
  if (!attributions.length) {
    return <p className="t-label text-ink-faint">No attribution available for this event.</p>
  }
  const max = Math.max(1e-6, ...attributions.map((a) => Math.abs(a.contribution)))

  return (
    <div onMouseLeave={() => onHover(null)}>
      <div className="t-micro mb-2 grid grid-cols-[minmax(0,1fr)_88px_92px] items-center gap-3 text-ink-faint">
        <span>Measurement</span>
        <span className="text-right">Measured</span>
        <span className="text-right">Contribution</span>
      </div>

      <ul className="flex flex-col gap-1">
        {attributions.map((a) => {
          const frac = Math.abs(a.contribution) / max
          const supports = a.contribution >= 0
          return (
            <li
              key={a.feature}
              onMouseEnter={() => onHover(a.feature)}
              className="grid grid-cols-[minmax(0,1fr)_88px_92px] items-center gap-3 rounded px-1 py-1 transition-colors duration-150 hover:bg-surface-2"
            >
              <div className="min-w-0">
                <div className="t-label truncate text-ink-dim">{a.label}</div>
                <div className="relative mt-1 h-1.5 rounded-full bg-surface-3">
                  <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
                  <div
                    className="absolute inset-y-0 rounded-full transition-[width] duration-300"
                    style={{
                      width: `${(frac * 50).toFixed(1)}%`,
                      left: supports ? '50%' : undefined,
                      right: supports ? undefined : '50%',
                      background: supports ? 'var(--color-fault)' : 'var(--color-normal)',
                    }}
                  />
                </div>
              </div>
              <span className="num t-label text-right text-ink-dim">{num(a.value)}</span>
              <span
                className="num t-label text-right"
                style={{ color: supports ? 'var(--color-fault)' : 'var(--color-normal)' }}
                title={supports ? 'Supports the diagnosis' : 'Argues against the diagnosis'}
              >
                {supports ? '+' : '−'}{num(Math.abs(a.contribution), 3)}
              </span>
            </li>
          )
        })}
      </ul>

      <p className="t-label mt-3 text-ink-faint">
        Bar length is the contribution, not the measurement.{' '}
        <span style={{ color: 'var(--color-fault)' }}>Right</span> supports the diagnosis,{' '}
        <span style={{ color: 'var(--color-normal)' }}>left</span> argues against it.
      </p>
    </div>
  )
}
