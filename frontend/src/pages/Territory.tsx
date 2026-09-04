import { useNavigate } from 'react-router-dom'
import { Schematic } from '../components/Schematic'
import { Empty, Note, Page, Panel } from '../shell/Page'
import { useConsole } from '../state/console'
import { SEVERITY_COLOR, ago, faultLabel, stateOf } from '../lib/format'

/**
 * Territory — the overview.
 *
 * One question: is anything wrong across the layout right now. The plan gets
 * the page to itself, which is what it needed; everything below it is there to
 * say which of those turnouts to look at first.
 */
export function Territory({ selected, onSelect }: { selected: string | null; onSelect: (id: string | null) => void }) {
  const { machines, events, recent, alerts, openAlerts, stats } = useConsole()
  const navigate = useNavigate()

  const attention = machines
    .filter((m) => stateOf(m.severity) !== 'clear')
    .sort((a, b) => a.health.health - b.health.health)

  const normN = machines.filter((m) => m.position === 'N').length
  const revN = machines.filter((m) => m.position === 'R').length

  return (
    <Page
      title="Territory"
      ko="선로도"
      lede="Interlocking plan for Sehwa depot. The lit leg of each turnout is the route the points are currently set for."
      actions={
        <div className="flex gap-4 px-4 py-[11px]"
          style={{ border: '1px solid var(--color-line)', background: 'var(--color-panel)', boxShadow: 'inset 0 1px 0 rgba(255,255,255,.05)' }}>
          <Stat k="TURNOUTS" v={String(machines.length)} c="var(--color-ink)" />
          <span aria-hidden className="w-px" style={{ background: 'var(--color-line)' }} />
          <Stat k="SET NORMAL" v={String(normN)} c="var(--color-green)" />
          <span aria-hidden className="w-px" style={{ background: 'var(--color-line)' }} />
          <Stat k="SET REVERSE" v={String(revN)} c="var(--color-cyan)" />
        </div>
      }
    >
      <div className="panel-deep">
        <div className="flex items-center justify-between border-b px-4 py-[11px]"
          style={{ borderColor: 'var(--color-edge)', background: 'var(--color-panel)' }}>
          <span className="sec">Sehwa depot · interlocking plan</span>
          <Note>SCHEMATIC · NOT TO SCALE</Note>
        </div>
        <div className="px-2.5 py-1.5"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,.022) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.022) 1px, transparent 1px)',
            backgroundSize: '34px 34px',
          }}>
          <Schematic machines={machines} selected={selected} recent={recent} onSelect={onSelect} />
        </div>
        <div className="flex flex-wrap items-center gap-x-[22px] gap-y-2 border-t px-4 py-2.5"
          style={{ borderColor: 'var(--color-edge)', background: 'var(--color-rail)' }}>
          {[
            { c: 'var(--color-green)', l: 'ROUTE SET · CLEAR' },
            { c: 'var(--color-amber)', l: 'WATCH' },
            { c: 'var(--color-accent)', l: 'FAULT' },
            { c: 'var(--color-idle)', l: 'UNSET LEG' },
          ].map((l) => (
            <span key={l.l} className="flex items-center gap-[7px]">
              <span aria-hidden className="inline-block h-[3px] w-4" style={{ background: l.c }} />
              <span className="mono text-[10px] leading-none" style={{ letterSpacing: '0.06em', color: 'var(--color-label)' }}>{l.l}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="grid items-start gap-[18px] xl:grid-cols-2">
        <Panel title="Needs attention" flush
          aside={<Note>{attention.length} OF {machines.length}</Note>}>
          {attention.length === 0 ? (
            <Empty>Every machine is operating within limits.</Empty>
          ) : (
            <div className="stagger">
              {attention.map((m) => {
                const colour = SEVERITY_COLOR[m.severity]
                const cause = alerts.find((a) => a.machine_id === m.id && a.state !== 'resolved')
                return (
                  <button key={m.id} type="button" onClick={() => onSelect(m.id)}
                    className="grid h-12 w-full grid-cols-[3px_74px_minmax(0,1fr)_46px_52px] items-center gap-3 border-b pr-4 text-left transition-colors hover:bg-raised"
                    style={{ borderColor: 'var(--color-hair)' }}>
                    <span aria-hidden className="h-12 w-[3px]" style={{ background: colour }} />
                    <span className="mono pl-[13px] text-[12px] font-medium leading-none" style={{ color: 'var(--color-ink-2)' }}>
                      {m.id}
                    </span>
                    <span className="flex min-w-0 flex-col gap-1">
                      <span className="truncate text-[12px] leading-none" style={{ color: 'var(--color-dim)' }}>
                        {cause ? faultLabel(cause.fault) : 'degrading health'}
                      </span>
                      <span className="truncate text-[11px] leading-none" style={{ color: 'var(--color-label)' }}>
                        {cause ? cause.fault_ko : `${ago(m.last_event_at)} ago`}
                      </span>
                    </span>
                    <span className="mono text-[12px] font-medium leading-none" style={{ color: colour }}>
                      {(m.health.health * 100).toFixed(0)}%
                    </span>
                    <span className="mono min-w-[44px] text-right text-[10px] uppercase leading-none"
                      style={{ letterSpacing: '0.1em', color: colour }}>
                      {stateOf(m.severity)}
                    </span>
                  </button>
                )
              })}
            </div>
          )}
        </Panel>

        <Panel title="Live throw log" flush
          aside={<Note>{stats?.events_streamed ?? 0} SEEN · {openAlerts.length} OPEN</Note>}>
          {events.length === 0 ? (
            <Empty>Waiting for the first throw.</Empty>
          ) : (
            <div>
              {events.slice(0, 12).map((e) => (
                <button key={e.id} type="button" onClick={() => navigate(`/events/${e.id}`)}
                  className="grid h-[34px] w-full grid-cols-[70px_44px_minmax(0,1fr)_58px_40px] items-center gap-2 border-b px-3.5 text-left transition-colors hover:bg-raised"
                  style={{ borderColor: 'var(--color-hair)' }}>
                  <span className="mono text-[11px] font-medium leading-none" style={{ color: 'var(--color-ink-4)' }}>{e.machine_id}</span>
                  <span className="mono text-[10px] font-medium leading-none"
                    style={{ letterSpacing: '0.06em', color: e.direction === 'N' ? 'var(--color-green)' : 'var(--color-cyan)' }}>
                    →{e.direction}
                  </span>
                  <span className="truncate text-[11px] leading-none" style={{ color: SEVERITY_COLOR[e.prediction.severity] }}>
                    {faultLabel(e.prediction.fault)}
                  </span>
                  <span className="mono text-right text-[11px] leading-none" style={{ color: 'var(--color-label)' }}>
                    {e.throw_samples} sa
                  </span>
                  <span className="mono text-right text-[11px] leading-none" style={{ color: 'var(--color-label)' }}>{ago(e.ts)}</span>
                </button>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </Page>
  )
}

function Stat({ k, v, c }: { k: string; v: string; c: string }) {
  return (
    <div className="flex flex-col gap-[5px]">
      <span className="cap">{k}</span>
      <span className="mono text-[14px] font-medium leading-none" style={{ color: c }}>{v}</span>
    </div>
  )
}
