import { useNavigate } from 'react-router-dom'
import { Schematic } from '../components/Schematic'
import { Sparkline } from '../components/Sparkline'
import { Empty, Page, Section } from '../shell/Page'
import { useConsole } from '../state/console'
import { POSITION_LABEL, SEVERITY_COLOR, ago, faultLabel, num } from '../lib/format'

/**
 * Territory — the overview.
 *
 * One question: is anything wrong across the layout right now. The schematic
 * finally has the page to itself, which is what it needed; clicking a machine
 * navigates to it rather than filtering something else on the same screen.
 */
export function Territory() {
  const { machines, events, recent, openAlerts } = useConsole()
  const navigate = useNavigate()

  const attention = machines
    .filter((m) => m.severity === 'critical' || m.severity === 'warning')
    .sort((a, b) => a.health.health - b.health.health)

  return (
    <Page
      title="Territory"
      ko="선로도"
      lede="Every point machine on the layout. The solid leg of each turnout is the route the points are set for."
    >
      <Section>
        <Schematic
          machines={machines}
          selected={null}
          recent={recent}
          onSelect={(id) => navigate(`/machines/${id}`)}
        />
      </Section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Section
          title="Needs attention"
          aside={<span className="t-label text-ink-faint">{attention.length} of {machines.length}</span>}
        >
          {attention.length === 0 ? (
            <Empty>Every machine is operating within limits.</Empty>
          ) : (
            <ul className="stagger flex flex-col gap-2">
              {attention.map((m) => (
                <li key={m.id}>
                  <button
                    onClick={() => navigate(`/machines/${m.id}`)}
                    className="press flex w-full items-center gap-3 rounded-lg bg-surface-2 px-3 py-2.5 text-left hover:bg-surface-3"
                  >
                    <span
                      aria-hidden
                      className="h-8 w-[3px] shrink-0 rounded-full"
                      style={{ background: SEVERITY_COLOR[m.severity] }}
                    />
                    <span className="min-w-0">
                      <span className="num t-label block font-semibold">{m.id}</span>
                      <span className="t-label block truncate text-ink-faint">
                        {POSITION_LABEL[m.position]} · {ago(m.last_event_at)} ago
                      </span>
                    </span>
                    <span className="ml-auto shrink-0 text-right">
                      <span className="t-metric block">{(m.health.health * 100).toFixed(0)}<span className="t-label text-ink-faint">%</span></span>
                      <span className="t-label block text-ink-faint">
                        {m.health.rul_cycles == null ? 'no failure ahead' : `${num(m.health.rul_cycles, 0)} throws left`}
                      </span>
                    </span>
                    <span className="hidden w-20 shrink-0 sm:block">
                      <Sparkline values={m.health.trend} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section
          title="Recent throws"
          aside={<span className="t-label text-ink-faint">{openAlerts.length} open alerts</span>}
        >
          <ul className="flex flex-col gap-0.5">
            {events.slice(0, 14).map((e) => (
              <li key={e.id}>
                <button
                  onClick={() => navigate(`/events/${e.id}`)}
                  className={`t-label flex w-full items-center gap-2 rounded px-1.5 py-1 text-left hover:bg-surface-2 ${
                    e.prediction.severity === 'normal' ? 'text-ink-faint' : 'text-ink'
                  }`}
                >
                  <span
                    className="shrink-0 rounded-full"
                    style={{
                      background: SEVERITY_COLOR[e.prediction.severity],
                      width: e.prediction.severity === 'normal' ? 3 : 6,
                      height: e.prediction.severity === 'normal' ? 3 : 6,
                      opacity: e.prediction.severity === 'normal' ? 0.5 : 1,
                    }}
                  />
                  <span className="num shrink-0">{e.machine_id}</span>
                  <span className="truncate">{faultLabel(e.prediction.fault)}</span>
                  <span className="num ml-auto shrink-0 text-ink-faint">{ago(e.ts)}</span>
                </button>
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </Page>
  )
}
