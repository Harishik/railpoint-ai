import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Empty, Page, Panel, Segmented } from '../shell/Page'
import { useConsole } from '../state/console'
import { SEVERITY_COLOR, ago, faultLabel } from '../lib/format'

type Filter = 'open' | 'resolved' | 'all'

/**
 * Alerts — the triage queue.
 *
 * Repeat conditions on one machine collapse into a single row with a count, so
 * a persistently degrading machine cannot bury the rest of the fleet under its
 * own repetitions.
 */
export function Alerts() {
  const { alerts, onAlertAction } = useConsole()
  const [filter, setFilter] = useState<Filter>('open')
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()

  // Arriving from a machine's inspector scopes the queue to that machine, and
  // the scope is visible and removable rather than a hidden mode.
  const scope = params.get('m')

  const inScope = scope ? alerts.filter((a) => a.machine_id === scope) : alerts
  const counts = {
    open: inScope.filter((a) => a.state !== 'resolved').length,
    resolved: inScope.filter((a) => a.state === 'resolved').length,
    all: inScope.length,
  }
  const shown = inScope.filter((a) =>
    filter === 'all' ? true : filter === 'open' ? a.state !== 'resolved' : a.state === 'resolved',
  )

  return (
    <Page
      title="Alerts"
      ko="경보"
      lede="Repeat conditions on one machine collapse into a single row with a count, so a persistently degrading machine cannot bury the rest."
      actions={
        <div className="flex items-center gap-2.5">
          {scope && (
            <button type="button"
              onClick={() => { const next = new URLSearchParams(params); next.delete('m'); setParams(next, { replace: true }) }}
              className="press mono inline-flex h-7 items-center gap-2 px-3 text-[11px] leading-none"
              style={{ border: '1px solid var(--color-rule)', background: 'var(--color-raised)', color: 'var(--color-ink-4)' }}>
              {scope} <span style={{ color: 'var(--color-label)' }}>×</span>
            </button>
          )}
          <Segmented value={filter} onChange={setFilter} label="Alert filter"
            options={[
              { value: 'open', label: 'Open', count: counts.open },
              { value: 'resolved', label: 'Resolved', count: counts.resolved },
              { value: 'all', label: 'All', count: counts.all },
            ]} />
        </div>
      }
    >
      <Panel flush>
        <div className="overflow-x-auto">
          <div className="min-w-[880px]">
            <div className="grid grid-cols-[78px_92px_minmax(0,1fr)_96px_84px_264px] items-center gap-3.5 border-b"
              style={{ height: 38, borderColor: 'var(--color-line)', background: 'var(--color-deep)' }}>
              <span className="cap pl-[18px]">Severity</span>
              <span className="cap">Machine</span>
              <span className="cap">Condition</span>
              <span className="cap">First seen</span>
              <span className="cap">Count</span>
              <span className="cap pr-[18px] text-right">Action</span>
            </div>

            {shown.length === 0 ? (
              <Empty>Nothing in this view.</Empty>
            ) : shown.map((a) => {
              const colour = SEVERITY_COLOR[a.severity]
              const sev = a.severity === 'critical' ? 'FAULT' : a.severity === 'warning' ? 'CAUTION' : 'INFO'
              const resolved = a.state === 'resolved'
              const acked = a.state === 'acknowledged'
              return (
                <div key={a.id}
                  className="grid grid-cols-[78px_92px_minmax(0,1fr)_96px_84px_264px] items-center gap-3.5 border-b transition-colors hover:bg-raised"
                  style={{ height: 58, borderColor: 'var(--color-hair)', opacity: resolved ? 0.42 : 1 }}>
                  <span className="flex h-[58px] items-center pl-[18px]">
                    <span className="mono inline-flex h-5 items-center px-2 text-[9px] font-semibold leading-none"
                      style={{
                        letterSpacing: '0.12em',
                        background: `color-mix(in srgb, ${colour} 10%, transparent)`,
                        borderLeft: `2px solid ${colour}`,
                        color: colour,
                      }}>
                      {sev}
                    </span>
                  </span>
                  <span className="mono text-[13px] font-medium leading-none" style={{ color: 'var(--color-ink)' }}>
                    {a.machine_id}
                  </span>
                  <span className="flex min-w-0 flex-col gap-1">
                    <span className="truncate text-[13px] font-medium leading-none" style={{ color: 'var(--color-ink-2)' }}>
                      {faultLabel(a.fault)}
                    </span>
                    <span className="truncate text-[11px] leading-none" style={{ color: 'var(--color-label)' }}>{a.fault_ko}</span>
                  </span>
                  <span className="mono text-[11px] leading-none" style={{ color: 'var(--color-dim)' }}>{ago(a.ts)}</span>
                  <span className="mono text-[11px] leading-none"
                    style={{ color: a.count > 1 ? 'var(--color-ink-2)' : 'var(--color-label)' }}
                    title={a.count > 1 ? `Raised on ${a.count} throws` : undefined}>
                    {a.count > 1 ? `×${a.count}` : '—'}
                  </span>
                  <span className="flex justify-end gap-[7px] pr-[18px]">
                    <Row onClick={() => navigate(`/events/${a.event_id}`)}>Waveform</Row>
                    {!resolved && (
                      <Row onClick={() => onAlertAction(a.id, 'acknowledge')} on={acked}>
                        {acked ? 'Acked' : 'Acknowledge'}
                      </Row>
                    )}
                    <Row go onClick={() => onAlertAction(a.id, resolved ? 'reopen' : 'resolve')}>
                      {resolved ? 'Reopen' : 'Resolve'}
                    </Row>
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </Panel>
    </Page>
  )
}

function Row({ children, onClick, on, go }: { children: React.ReactNode; onClick: () => void; on?: boolean; go?: boolean }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on}
      className="press inline-flex h-[27px] items-center px-[11px] text-[11px] font-medium leading-none hover:border-rule-hi"
      style={go
        ? { border: '1px solid #1D3A2C', background: 'rgba(63,214,140,.08)', color: 'var(--color-green)' }
        : {
            border: `1px solid ${on ? 'var(--color-rule-hi)' : 'var(--color-rule)'}`,
            background: on ? 'var(--color-line)' : 'var(--color-raised)',
            color: on ? 'var(--color-ink)' : 'var(--color-ink-4)',
          }}>
      {children}
    </button>
  )
}
