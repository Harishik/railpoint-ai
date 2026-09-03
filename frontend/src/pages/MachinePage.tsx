import { useNavigate, useParams } from 'react-router-dom'
import { Empty, Page, Section } from '../shell/Page'
import { Sparkline } from '../components/Sparkline'
import { useConsole } from '../state/console'
import { POSITION_COLOR, POSITION_LABEL, SEVERITY_COLOR, ago, faultLabel, num } from '../lib/format'

/** One machine: its condition, its remaining life, and everything it has done. */
export function MachinePage() {
  const { machineId } = useParams()
  const { machine, eventsFor, alerts } = useConsole()
  const navigate = useNavigate()
  const m = machine(machineId)
  const events = eventsFor(machineId ?? null)
  const machineAlerts = alerts.filter((a) => a.machine_id === machineId && a.state !== 'resolved')

  if (!m) {
    return (
      <Page title={machineId ?? 'Machine'}>
        <Section><Empty>No such machine on this layout.</Empty></Section>
      </Page>
    )
  }

  const rul = m.health.rul_cycles

  return (
    <Page
      title={m.id}
      ko={POSITION_LABEL[m.position]}
      lede={`${m.spec} · last throw ${ago(m.last_event_at)} ago · ${m.events_today} throws seen`}
      actions={
        <span
          className="t-label rounded-full px-2.5 py-1 font-semibold capitalize"
          style={{
            background: `color-mix(in oklch, ${SEVERITY_COLOR[m.severity]} 16%, transparent)`,
            color: SEVERITY_COLOR[m.severity],
          }}
        >
          {m.severity}
        </span>
      }
    >
      <div className="grid gap-4 md:grid-cols-3">
        <Section title="Health index" aside={<span className="t-label text-ink-faint">건전성</span>}>
          <div className="flex items-end justify-between gap-3">
            <span className="t-display" style={{ color: POSITION_COLOR[m.position] }}>
              {(m.health.health * 100).toFixed(0)}<span className="t-label text-ink-faint">%</span>
            </span>
            <span className="h-10 w-28"><Sparkline values={m.health.trend} /></span>
          </div>
        </Section>

        <Section title="Remaining life" aside={<span className="t-label text-ink-faint">잔여 수명</span>}>
          {rul == null ? (
            <>
              <span className="t-display text-ink-dim">—</span>
              <p className="t-label mt-1 text-ink-faint">
                No failure ahead of this machine in the horizon. Censored, not zero.
              </p>
            </>
          ) : (
            <>
              <span className="t-display">{num(rul, 0)}<span className="t-label text-ink-faint"> throws</span></span>
              <p className="t-label mt-1 text-ink-faint">
                90% interval {num(m.health.rul_low, 0)}–{num(m.health.rul_high, 0)}
              </p>
            </>
          )}
        </Section>

        <Section title="Position" aside={<span className="t-label text-ink-faint">현재 위치</span>}>
          <span className="t-display" style={{ color: POSITION_COLOR[m.position] }}>
            {m.position === 'transit' ? '—' : m.position}
          </span>
          <p className="t-label mt-1 text-ink-faint">{POSITION_LABEL[m.position]}</p>
        </Section>
      </div>

      {machineAlerts.length > 0 && (
        <Section title="Open alerts">
          <ul className="flex flex-col gap-1.5">
            {machineAlerts.map((a) => (
              <li key={a.id} className="relative overflow-hidden rounded-lg bg-surface-2 py-2 pl-3 pr-2">
                <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]" style={{ background: SEVERITY_COLOR[a.severity] }} />
                <span className="t-label">{faultLabel(a.fault)}</span>
                <span className="t-label ml-2 text-ink-faint">{a.fault_ko} · {ago(a.ts)} ago</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Throw history" aside={<span className="t-label text-ink-faint">{events.length} recorded</span>}>
        {events.length === 0 ? (
          <Empty>No throws recorded for this machine yet.</Empty>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {events.slice(0, 40).map((e) => (
              <li key={e.id}>
                <button
                  onClick={() => navigate(`/events/${e.id}`)}
                  className={`t-label flex w-full items-center gap-2 rounded px-1.5 py-1.5 text-left hover:bg-surface-2 ${
                    e.prediction.severity === 'normal' ? 'text-ink-faint' : 'text-ink'
                  }`}
                >
                  <span className="shrink-0 rounded-full"
                    style={{
                      background: SEVERITY_COLOR[e.prediction.severity],
                      width: e.prediction.severity === 'normal' ? 3 : 6,
                      height: e.prediction.severity === 'normal' ? 3 : 6,
                    }} />
                  <span className="num shrink-0">{e.id}</span>
                  <span className="truncate">{faultLabel(e.prediction.fault)}</span>
                  <span className="num shrink-0 text-ink-faint">{e.direction}</span>
                  <span className="num ml-auto shrink-0 text-ink-faint">{ago(e.ts)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </Page>
  )
}
