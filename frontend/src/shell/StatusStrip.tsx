import { useEffect, useState } from 'react'
import { useConsole } from '../state/console'
import { ago, stateOf } from '../lib/format'

/**
 * Status strip.
 *
 * Navigation lives in the rail, so this carries only the answer to "does
 * anything need me right now". Three counters at display size, then a run of
 * secondary readings, then whether the feed is actually live.
 *
 * Everything here is measured. The prototype's strip also carried link uptime
 * and per-throw inference latency; neither is instrumented, so rather than
 * print a plausible number they are not shown at all. A console that invents
 * one figure is a console whose other figures have to be checked.
 */
export function StatusStrip() {
  const { stats, events, machines, connected, bootError } = useConsole()

  // Local, so the clock ticks without re-rendering the whole console on the
  // three-second stream cadence.
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const counts = { fault: 0, watch: 0, clear: 0 }
  for (const m of machines) counts[stateOf(m.severity)] += 1

  const throwSamples = events.filter((e) => e.completed).map((e) => e.throw_samples)
  const meanThrow = throwSamples.length
    ? Math.round(throwSamples.reduce((a, b) => a + b, 0) / throwSamples.length)
    : null

  const strip: { k: string; v: string; color?: string }[] = [
    {
      k: 'OPEN ALERTS',
      v: String(stats?.open_alerts ?? 0),
      color: stats?.open_alerts ? 'var(--color-accent)' : 'var(--color-green)',
    },
    { k: 'THROWS SEEN', v: String(stats?.events_streamed ?? 0) },
    { k: 'MEAN THROW', v: meanThrow == null ? '—' : `${meanThrow} sa` },
    { k: 'LAST THROW', v: events[0] ? ago(events[0].ts) : '—' },
    { k: 'CADENCE', v: stats ? `${stats.stream_interval_s}s` : '—' },
  ]

  const live = connected && !bootError

  return (
    <header
      className="flex h-[62px] min-w-0 items-stretch border-b"
      style={{
        borderColor: 'var(--color-edge)',
        background: 'linear-gradient(180deg, var(--color-shell), var(--color-rail))',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,.045)',
      }}
    >
      <div className="flex flex-none items-center gap-[13px] border-r pl-[22px] pr-5"
        style={{ borderColor: 'var(--color-edge)' }}>
        <Count n={counts.fault} label="FAULT" colour="var(--color-accent)" />
        <Count n={counts.watch} label="WATCH" colour="var(--color-amber)" />
        <Count n={counts.clear} label="CLEAR" colour="var(--color-green)" />
      </div>

      <div className="flex min-w-0 flex-1 items-stretch overflow-hidden">
        {strip.map((c) => (
          <div key={c.k} className="flex flex-none flex-col justify-center gap-[5px] border-r px-5"
            style={{ borderColor: 'var(--color-edge)' }}>
            <span className="cap whitespace-nowrap">{c.k}</span>
            <span className="mono whitespace-nowrap text-[13px] font-medium leading-none"
              style={{ color: c.color ?? 'var(--color-ink)' }}>
              {c.v}
            </span>
          </div>
        ))}
      </div>

      <div className="flex flex-none items-center gap-2.5 px-[22px]">
        <div className="flex h-[26px] items-center gap-1.5 px-[9px]"
          style={{
            border: `1px solid ${live ? '#1D3A2C' : '#3A2E14'}`,
            background: live ? 'rgba(63,214,140,.07)' : 'rgba(242,179,61,.07)',
          }}
          title={bootError ?? (connected ? 'Live feed connected' : 'Reconnecting to the feed')}>
          <span aria-hidden className={`h-[5px] w-[5px] rounded-full ${live ? 'pulse-live' : ''}`}
            style={{ background: live ? 'var(--color-green)' : 'var(--color-amber)' }} />
          <span className="mono text-[10px] font-medium leading-none"
            style={{ letterSpacing: '0.1em', color: live ? 'var(--color-green)' : 'var(--color-amber)' }}>
            {live ? 'LIVE' : connected ? 'LOADING' : 'RECONNECTING'}
          </span>
        </div>
        <span className="mono hidden text-[12px] leading-none xl:inline" style={{ color: 'var(--color-label)' }}>
          {now.toTimeString().slice(0, 8)}
        </span>
      </div>
    </header>
  )
}

function Count({ n, label, colour }: { n: number; label: string; colour: string }) {
  return (
    <div className="flex items-baseline gap-[5px]">
      <span className="mono text-[22px] font-semibold leading-none" style={{ color: n === 0 ? 'var(--color-label)' : colour }}>
        {n}
      </span>
      <span className="mono text-[10px] font-medium leading-none" style={{ letterSpacing: '0.1em', color: 'var(--color-label)' }}>
        {label}
      </span>
    </div>
  )
}
