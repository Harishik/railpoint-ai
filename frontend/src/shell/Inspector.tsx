import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkline } from '../components/Sparkline'
import { useConsole } from '../state/console'
import { POSITION_COLOR, POSITION_KO, POSITION_LABEL, SEVERITY_COLOR, ago, faultLabel, num, stateOf } from '../lib/format'

/**
 * Machine inspector.
 *
 * A drawer rather than a page, because it is nearly always opened *while*
 * reading something else — a turnout on the plan, a row in the fleet — and
 * navigating away to answer "what is wrong with 007" costs the operator the
 * context that made them ask.
 *
 * It is driven by a `?m=` search parameter, not component state, so the drawer
 * is still linkable, the back button still closes it, and a link to one machine
 * still opens on the page it was sent from.
 */
export function Inspector({ id, onClose }: { id: string; onClose: () => void }) {
  const { machine, alerts, eventsFor } = useConsole()
  const navigate = useNavigate()
  const m = machine(id)

  // A drawer that traps you is worse than no drawer.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!m) return null

  const st = stateOf(m.severity)
  const colour = SEVERITY_COLOR[m.severity]
  const open = alerts.filter((a) => a.machine_id === id && a.state !== 'resolved')
  const events = eventsFor(id)
  const latest = events[0]
  const rul = m.health.rul_cycles

  // The interval bar is drawn on a fixed 700-throw ruler so two machines can be
  // compared by eye. Anything beyond that is clamped, and the numbers below the
  // bar always give the true bounds.
  const pct = (v: number | null) => `${(Math.min(Math.max(v ?? 0, 0), 700) / 700 * 100).toFixed(1)}%`

  return (
    <aside
      className="slide-in fixed inset-y-0 right-0 z-40 flex w-[392px] max-w-full flex-col border-l"
      style={{ borderColor: 'var(--color-line)', background: 'var(--color-inspector)', boxShadow: '-24px 0 60px rgba(0,0,0,.55)' }}
      role="complementary"
      aria-label={`${m.id} detail`}
    >
      <div className="flex items-start justify-between gap-3 border-b px-5 pb-4 pt-5"
        style={{ borderColor: 'var(--color-edge)', background: 'var(--color-shell)' }}>
        <div className="min-w-0">
          <div className="flex items-center gap-[9px]">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ background: colour }} />
            <span className="mono text-[18px] font-semibold leading-none tracking-[-0.02em]" style={{ color: 'var(--color-ink-hi)' }}>
              {m.id}
            </span>
            <span className="mono inline-flex h-[19px] items-center px-[7px] text-[9px] font-semibold uppercase leading-none"
              style={{ letterSpacing: '0.12em', color: colour, background: `color-mix(in srgb, ${colour} 12%, transparent)` }}>
              {st}
            </span>
          </div>
          <div className="mt-2 text-[12px] leading-none" style={{ color: 'var(--color-label)' }}>
            {m.spec} · {m.events_today} throws seen
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close inspector"
          className="press mono inline-flex h-7 w-7 flex-none items-center justify-center text-[14px] leading-none hover:border-rule-hi"
          style={{ border: '1px solid var(--color-rule)', color: 'var(--color-dim)' }}>
          ×
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-[18px] overflow-y-auto px-5 pb-6 pt-[18px]">
        <div className="grid grid-cols-2 gap-px border" style={{ background: 'var(--color-edge)', borderColor: 'var(--color-edge)' }}>
          {[
            { k: 'HEALTH', v: `${(m.health.health * 100).toFixed(0)}%`, c: colour },
            { k: 'POSITION', v: POSITION_LABEL[m.position], c: POSITION_COLOR[m.position] },
            { k: 'LAST THROW', v: ago(m.last_event_at), c: 'var(--color-ink-2)' },
            { k: 'LAST VERDICT', v: latest ? faultLabel(latest.prediction.fault) : '—', c: latest ? SEVERITY_COLOR[latest.prediction.severity] : 'var(--color-label)' },
          ].map((s) => (
            <div key={s.k} className="flex flex-col gap-[7px] px-3.5 py-[13px]" style={{ background: 'var(--color-panel)' }}>
              <span className="cap">{s.k}</span>
              <span className="mono truncate text-[15px] font-medium leading-none" style={{ color: s.c }}>{s.v}</span>
            </div>
          ))}
        </div>

        <div className="flex flex-col gap-2.5">
          <span className="cap">Remaining life · 90% interval</span>
          {rul == null ? (
            <p className="text-[12px] leading-[1.5]" style={{ color: 'var(--color-label)' }}>
              No failure ahead of this machine within the horizon. Censored, not zero.
            </p>
          ) : (
            <>
              <div className="relative h-[26px]" style={{ background: 'var(--color-deep)', border: '1px solid var(--color-line)' }}>
                <div className="absolute inset-y-0" style={{
                  left: pct(m.health.rul_low),
                  width: `calc(${pct(m.health.rul_high)} - ${pct(m.health.rul_low)})`,
                  background: 'rgba(79,184,232,.18)',
                }} />
                <div className="absolute -top-[3px] -bottom-[3px] w-0.5" style={{ left: pct(rul), background: colour }} />
              </div>
              <div className="mono flex justify-between text-[10px] leading-none" style={{ color: 'var(--color-label)' }}>
                <span>{num(m.health.rul_low, 0)}</span>
                <span style={{ color: 'var(--color-ink-4)' }}>{num(rul, 0)} throws</span>
                <span>{num(m.health.rul_high, 0)}</span>
              </div>
            </>
          )}
        </div>

        <div className="flex flex-col gap-2.5">
          <span className="cap">Health · last {m.health.trend.length} throws</span>
          <div className="p-3" style={{ border: '1px solid var(--color-line)', background: 'var(--color-deep)' }}>
            <Sparkline values={m.health.trend} width={320} height={76} colour={colour} strokeWidth={1.8} tip={false} />
          </div>
        </div>

        <div className="flex flex-col">
          <span className="cap pb-[9px]">Open conditions</span>
          {open.length === 0 ? (
            <p className="py-2 text-[12px] leading-none" style={{ color: 'var(--color-label)' }}>
              No open conditions. Operating within limits.
            </p>
          ) : open.map((a) => (
            <div key={a.id} className="grid h-[42px] grid-cols-[2px_1fr_auto] items-center gap-[11px] border-b"
              style={{ borderColor: 'var(--color-hair)' }}>
              <span aria-hidden className="h-[42px] w-0.5" style={{ background: SEVERITY_COLOR[a.severity] }} />
              <span className="flex min-w-0 flex-col gap-[3px]">
                <span className="truncate text-[12px] font-medium leading-none" style={{ color: 'var(--color-ink-2)' }}>
                  {faultLabel(a.fault)}
                </span>
                <span className="truncate text-[10px] leading-none" style={{ color: 'var(--color-label)' }}>{a.fault_ko}</span>
              </span>
              <span className="mono text-[10px] leading-none" style={{ color: 'var(--color-label)' }}>{ago(a.ts)}</span>
            </div>
          ))}
        </div>

        <div className="flex flex-col">
          <span className="cap pb-[9px]">Recent throws</span>
          {events.length === 0 ? (
            <p className="py-2 text-[12px] leading-none" style={{ color: 'var(--color-label)' }}>
              No throws recorded for this machine yet.
            </p>
          ) : events.slice(0, 12).map((e) => (
            <button key={e.id} type="button" onClick={() => navigate(`/events/${e.id}`)}
              className="grid h-[34px] grid-cols-[68px_34px_minmax(0,1fr)_38px] items-center gap-2 border-b px-0 text-left transition-colors hover:bg-raised"
              style={{ borderColor: 'var(--color-hair)' }}>
              <span className="mono text-[11px] leading-none" style={{ color: 'var(--color-ink-4)' }}>{e.id}</span>
              <span className="mono text-[10px] leading-none" style={{ color: POSITION_COLOR[e.direction] }}>{e.direction}</span>
              <span className="truncate text-[11px] leading-none" style={{ color: SEVERITY_COLOR[e.prediction.severity] }}>
                {faultLabel(e.prediction.fault)}
              </span>
              <span className="mono text-right text-[11px] leading-none" style={{ color: 'var(--color-label)' }}>{ago(e.ts)}</span>
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          <button type="button" disabled={!latest}
            onClick={() => latest && navigate(`/events/${latest.id}`)}
            className="press inline-flex h-[34px] flex-1 items-center justify-center text-[12px] font-semibold leading-none disabled:opacity-40"
            style={{ background: 'var(--color-accent)', color: 'var(--color-bg)' }}>
            Open waveform
          </button>
          <button type="button" onClick={() => navigate(`/alerts?m=${m.id}`)}
            className="press inline-flex h-[34px] flex-1 items-center justify-center text-[12px] font-medium leading-none hover:border-rule-hi"
            style={{ border: '1px solid var(--color-rule)', background: 'var(--color-raised)', color: 'var(--color-ink-4)' }}>
            Alert history
          </button>
        </div>
      </div>

      <p className="sr-only">{POSITION_KO[m.position]}</p>
    </aside>
  )
}
