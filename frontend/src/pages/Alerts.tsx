import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Empty, Page, Section } from '../shell/Page'
import { useConsole } from '../state/console'
import { SEVERITY_COLOR, ago, faultLabel } from '../lib/format'

type Filter = 'open' | 'all' | 'resolved'

/**
 * Alerts — the triage queue.
 *
 * Given its own page the queue can show what a cramped side panel could not:
 * why the alert was raised, how many throws have repeated it, and a route
 * straight to the waveform that produced it.
 */
export function Alerts() {
  const { alerts, onAlertAction } = useConsole()
  const [filter, setFilter] = useState<Filter>('open')
  const navigate = useNavigate()

  const shown = alerts.filter((a) =>
    filter === 'all' ? true : filter === 'open' ? a.state !== 'resolved' : a.state === 'resolved',
  )

  return (
    <Page
      title="Alerts"
      ko="경보"
      lede="Repeat conditions on one machine collapse into a single row with a count, so a persistently degrading machine cannot bury the rest."
      actions={
        <div className="flex gap-1 rounded-lg bg-surface-2 p-1" role="tablist" aria-label="Alert filter">
          {(['open', 'resolved', 'all'] as Filter[]).map((f) => (
            <button
              key={f}
              role="tab"
              aria-selected={filter === f}
              onClick={() => setFilter(f)}
              className={`press t-label rounded-md px-2.5 py-1 capitalize ${
                filter === f ? 'bg-surface-3 text-ink' : 'text-ink-dim hover:text-ink'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      }
    >
      <Section>
        {shown.length === 0 ? (
          <Empty>Nothing here. The fleet is operating within limits.</Empty>
        ) : (
          <ul className="stagger flex flex-col gap-2">
            {shown.map((a) => {
              const triaged = a.state !== 'open'
              return (
                <li
                  key={a.id}
                  className="relative overflow-hidden rounded-lg bg-surface-2 transition-opacity"
                  style={{ opacity: triaged ? 0.66 : 1 }}
                >
                  <span aria-hidden className="absolute inset-y-0 left-0 w-[3px]"
                    style={{ background: SEVERITY_COLOR[a.severity] }} />
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 pl-4 pr-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-2">
                        <button
                          onClick={() => navigate(`/machines/${a.machine_id}`)}
                          className="num t-label font-semibold underline-offset-2 hover:underline"
                        >
                          {a.machine_id}
                        </button>
                        <span className="t-label text-ink">{faultLabel(a.fault)}</span>
                        <span className="t-label text-ink-faint">{a.fault_ko}</span>
                        {a.count > 1 && (
                          <span className="num rounded-full bg-surface-3 px-1.5 text-[10px] text-ink-faint"
                            title={`Raised on ${a.count} throws`}>
                            ×{a.count}
                          </span>
                        )}
                      </div>
                      <div className="t-label mt-0.5 text-ink-faint">
                        first seen {ago(a.ts)} ago
                        {a.last_ts && a.last_ts !== a.ts && <> · last {ago(a.last_ts)} ago</>}
                        {triaged && <> · {a.state}</>}
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-1.5">
                      <button
                        onClick={() => navigate(`/events/${a.event_id}`)}
                        className="press t-label rounded-md border border-line px-2 py-1 text-ink-dim hover:border-line-strong hover:text-ink"
                      >
                        Waveform
                      </button>
                      {a.state === 'open' && (
                        <button onClick={() => onAlertAction(a.id, 'acknowledge')}
                          className="press t-label rounded-md border border-line px-2 py-1 text-ink-dim hover:border-line-strong hover:text-ink">
                          Acknowledge
                        </button>
                      )}
                      {a.state !== 'resolved' && (
                        <button onClick={() => onAlertAction(a.id, 'resolve')}
                          className="press t-label rounded-md border border-line px-2 py-1 text-ink-dim hover:border-line-strong hover:text-ink">
                          Resolve
                        </button>
                      )}
                      {a.state === 'resolved' && (
                        <button onClick={() => onAlertAction(a.id, 'reopen')}
                          className="press t-label rounded-md border border-line px-2 py-1 text-ink-dim hover:border-line-strong hover:text-ink">
                          Undo
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </Section>
    </Page>
  )
}
