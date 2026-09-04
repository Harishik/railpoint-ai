import type { Attribution } from '../lib/types'
import { num } from '../lib/format'

interface Props {
  attributions: Attribution[]
  onHover: (feature: string | null) => void
}

/**
 * Local attribution.
 *
 * Bars diverge from a zero line so the *direction* of evidence reads at a
 * glance — supporting the verdict, or arguing against it — and hovering one
 * lights the waveform phase it came from.
 *
 * The measured value and the contribution are separate columns on purpose.
 * They were briefly the same number, which is how a chart misleads without
 * ever being wrong: a long bar sat beside "188.00" and read as if the bar
 * meant 188. The bar is a signed z-score against healthy operation; the column
 * is the measurement in its own units.
 *
 * The zero line is placed from the data rather than fixed, so a set of
 * attributions that is entirely one-signed uses the full width instead of
 * cramming into a quarter of it.
 */
export function Evidence({ attributions, onHover }: Props) {
  if (!attributions.length) {
    return <p className="text-[12px]" style={{ color: 'var(--color-label)' }}>No attribution available for this event.</p>
  }

  const maxPos = Math.max(0, ...attributions.map((a) => a.contribution))
  const maxNeg = Math.max(0, ...attributions.map((a) => -a.contribution))
  const span = maxPos + maxNeg || 1
  // Clamped so a single tiny counter-signal still leaves a readable stub of
  // track on its side of the line.
  const zero = Math.min(85, Math.max(15, (maxNeg / span) * 100))

  return (
    <div onMouseLeave={() => onHover(null)}>
      <div className="grid grid-cols-[minmax(0,1fr)_60px] gap-3.5 border-b px-[18px] pb-[5px] pt-[9px]"
        style={{ borderColor: 'var(--color-hair)' }}>
        <span className="cap" style={{ letterSpacing: '0.13em' }}>Measurement</span>
        <span className="cap text-right" style={{ letterSpacing: '0.13em' }}>Value</span>
      </div>

      <ul>
        {attributions.map((a) => {
          const supports = a.contribution >= 0
          const w = supports
            ? (maxPos ? (a.contribution / maxPos) * (100 - zero) : 0)
            : (maxNeg ? (-a.contribution / maxNeg) * zero : 0)
          const colour = supports ? 'var(--color-accent)' : 'var(--color-cyan)'
          return (
            <li key={a.feature}
              onMouseEnter={() => onHover(a.feature)}
              className="grid h-[46px] grid-cols-[minmax(0,1fr)_60px] items-center gap-3.5 border-b px-[18px] transition-colors hover:bg-raised"
              style={{ borderColor: 'var(--color-hair)' }}>
              <span className="flex min-w-0 flex-col gap-1.5">
                <span className="flex items-baseline justify-between gap-3">
                  <span className="truncate text-[12px] leading-none" style={{ color: 'var(--color-ink-3)' }}>{a.label}</span>
                  <span className="mono flex-none text-[11px] font-medium leading-none" style={{ color: colour }}
                    title={supports ? 'Supports the verdict' : 'Argues against the verdict'}>
                    {supports ? '+' : '−'}{num(Math.abs(a.contribution), 3)}
                  </span>
                </span>
                <span className="relative block h-[5px]" style={{ background: 'var(--color-hair)' }}>
                  <span className="absolute inset-y-0 w-px" style={{ left: `${zero}%`, background: 'var(--color-tick)' }} />
                  <span className="absolute inset-y-0 transition-[width,left] duration-300"
                    style={{
                      left: `${supports ? zero : zero - w}%`,
                      width: `${w}%`,
                      background: colour,
                    }} />
                </span>
              </span>
              <span className="mono text-right text-[12px] font-medium leading-none" style={{ color: 'var(--color-dim)' }}>
                {num(a.value)}
              </span>
            </li>
          )
        })}
      </ul>

      <p className="px-[18px] py-3 text-[11px] leading-[1.5]" style={{ color: 'var(--color-label)' }}>
        Bar length is the contribution, not the measurement.{' '}
        <span style={{ color: 'var(--color-accent)' }}>Right</span> supports the verdict,{' '}
        <span style={{ color: 'var(--color-cyan)' }}>left</span> argues against it.
      </p>
    </div>
  )
}
